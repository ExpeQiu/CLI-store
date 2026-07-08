from sqlalchemy import Column, Integer, String, DateTime, Text, Float, JSON
from sqlalchemy.sql import func
from app.core.database import Base

class EventTask(Base):
    """发布会监控任务表"""
    __tablename__ = "event_tasks"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String(50), index=True)  # bilibili, douyin, etc.
    room_id = Column(String(100), index=True)
    event_name = Column(String(200))
    car_brand = Column(String(100))
    car_model = Column(String(200))
    event_id = Column(String(100), index=True)
    status = Column(String(20), default="running") # running, stopped
    start_time = Column(DateTime(timezone=True), server_default=func.now())
    end_time = Column(DateTime(timezone=True), nullable=True)

class LiveMetric(Base):
    """直播间实时热度指标（分钟级聚合）"""
    __tablename__ = "live_metrics"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    online_count = Column(Integer, default=0)  # 在线人数
    like_count = Column(Integer, default=0)    # 点赞数
    danmaku_density = Column(Integer, default=0) # 该分钟内的弹幕数量

class DanmakuRecord(Base):
    """弹幕原始记录"""
    __tablename__ = "danmaku_records"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    user_name = Column(String(100))
    user_id = Column(String(100), index=True, nullable=True) # 增加用户ID
    user_level = Column(Integer, nullable=True) # 增加用户等级/粉丝牌级别
    content = Column(Text)
    
class DanmakuAnalysis(Base):
    """弹幕 NLP 分析结果"""
    __tablename__ = "danmaku_analysis"

    id = Column(Integer, primary_key=True, index=True)
    danmaku_id = Column(Integer, index=True, unique=True) # 关联 DanmakuRecord 的 ID
    task_id = Column(Integer, index=True)
    sentiment_score = Column(Float, nullable=True) # 情感得分: -1.0 到 1.0
    intent_score = Column(Float, nullable=True) # 购买意向评分: 0-10
    keywords = Column(JSON, nullable=True) # 提取的关键词

class InteractionEvent(Base):
    """特殊互动事件（如送礼）"""
    __tablename__ = "interaction_events"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    user_name = Column(String(100))
    gift_name = Column(String(100))
    gift_value = Column(Float, default=0.0)
