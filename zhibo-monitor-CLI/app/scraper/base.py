import asyncio
import time
from typing import Dict, List, Optional, Any
from playwright.async_api import async_playwright, Browser, Page
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.schema import DanmakuRecord, EventTask, LiveMetric

class BaseScraper:
    def __init__(
        self,
        room_id: str,
        platform: str,
        event_name: Optional[str] = None,
        car_brand: Optional[str] = None,
        car_model: Optional[str] = None,
        event_id: Optional[str] = None,
        headless: bool = True,
        batch_size: int = 100,
        batch_interval: int = 5,
        storage_state: Optional[str] = None,
    ):
        self.room_id = room_id
        self.platform = platform
        self.event_name = event_name or f"{platform}-{room_id}"
        self.car_brand = car_brand or "unknown"
        self.car_model = car_model or ""
        self.event_id = event_id
        self.headless = headless
        self.storage_state = storage_state
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context = None
        self.page: Optional[Page] = None
        self.is_running = False
        self.task_id: Optional[int] = None
        
        # 批量写入相关配置
        self.batch_size = batch_size
        self.batch_interval = batch_interval
        self._danmaku_buffer: List[Dict[str, Any]] = []
        self._last_flush_time = time.time()
        self._flush_task: Optional[asyncio.Task] = None

    async def start(self):
        """启动浏览器并打开直播间"""
        self.playwright = await async_playwright().start()
        # 默认使用无头模式；调试选择器时可关闭无头模式。
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        if self.storage_state:
            self.context = await self.browser.new_context(storage_state=self.storage_state)
        else:
            self.context = await self.browser.new_context()
        self.page = await self.context.new_page()
        self.is_running = True
        self.task_id = self._create_task()
        self._flush_task = asyncio.create_task(self._auto_flush_loop())
        print(f"[{self.platform}] 启动采集，房间号: {self.room_id}")

    async def stop(self):
        """停止采集并释放资源"""
        self.is_running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        
        # 最后强制刷新一次缓冲
        if self._danmaku_buffer:
            self._do_flush_buffer()

        self._finish_task()
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        print(f"[{self.platform}] 停止采集，房间号: {self.room_id}")

    def _create_task(self) -> int:
        db: Session = SessionLocal()
        try:
            task = EventTask(
                platform=self.platform,
                room_id=self.room_id,
                event_name=self.event_name,
                car_brand=self.car_brand,
                car_model=self.car_model or None,
                event_id=self.event_id,
                status="running",
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            return task.id
        finally:
            db.close()

    def _finish_task(self) -> None:
        if not self.task_id:
            return

        db: Session = SessionLocal()
        try:
            task = db.get(EventTask, self.task_id)
            if task:
                task.status = "stopped"
                db.commit()
        finally:
            db.close()

    def flush_danmaku_records(
        self,
        danmakus: List[Dict[str, Any]],
        online_count: int = 0,
        like_count: int = 0,
    ) -> None:
        """将弹幕和实时指标放入内存缓冲，触发自动或手动落库。"""
        if not self.task_id:
            raise RuntimeError("采集任务尚未初始化，无法落库")

        if danmakus:
            self._danmaku_buffer.extend(danmakus)

        # 实时指标不需要缓冲，依然直接落库（因为数据量极小，通常每分钟一次）
        if online_count > 0 or like_count > 0:
            db: Session = SessionLocal()
            try:
                metric = LiveMetric(
                    task_id=self.task_id,
                    online_count=online_count,
                    like_count=like_count,
                    danmaku_density=len(danmakus),
                )
                db.add(metric)
                db.commit()
            except Exception as e:
                print(f"写入实时指标失败: {e}")
                db.rollback()
            finally:
                db.close()

        # 检查是否达到缓冲区大小阈值
        if len(self._danmaku_buffer) >= self.batch_size:
            self._do_flush_buffer()

    async def _auto_flush_loop(self):
        """后台协程，定时检查并刷新缓冲区"""
        while self.is_running:
            await asyncio.sleep(1) # 每秒检查一次
            current_time = time.time()
            if self._danmaku_buffer and (current_time - self._last_flush_time) >= self.batch_interval:
                self._do_flush_buffer()

    def _do_flush_buffer(self):
        """执行实际的批量落库操作"""
        if not self._danmaku_buffer or not self.task_id:
            return
        
        # 复制并清空当前缓冲区
        records_to_insert = list(self._danmaku_buffer)
        self._danmaku_buffer.clear()
        self._last_flush_time = time.time()

        db: Session = SessionLocal()
        try:
            records = [
                DanmakuRecord(
                    task_id=self.task_id,
                    user_name=item.get("user_name", ""),
                    user_id=item.get("user_id"),
                    user_level=item.get("user_level"),
                    content=item.get("content", ""),
                )
                for item in records_to_insert
            ]
            db.bulk_save_objects(records)
            db.commit()
            # print(f"[{self.platform}] 批量写入 {len(records)} 条弹幕数据")
        except Exception as e:
            print(f"批量写入弹幕失败: {e}")
            db.rollback()
            # 若失败可考虑将数据塞回 buffer 或者记录日志
        finally:
            db.close()

    async def run_loop(self):
        """主循环，子类需重写此方法"""
        raise NotImplementedError("子类必须实现 run_loop 方法")
