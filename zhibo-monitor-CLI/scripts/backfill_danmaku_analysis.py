from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from app.core.database import SessionLocal  # noqa: E402
from app.models.schema import DanmakuAnalysis, DanmakuRecord, EventTask  # noqa: E402


POSITIVE_HINTS = [
    "期待",
    "真香",
    "好",
    "可以",
    "有点东西",
    "不错",
    "厉害",
    "牛",
    "领先",
    "喜欢",
    "普及",
    "good",
]

NEGATIVE_HINTS = [
    "太贵",
    "贵",
    "不行",
    "慢",
    "难",
    "救一救",
    "没有",
    "问题",
    "担心",
    "丑",
    "落不了",
]

HIGH_INTENT_HINTS = [
    "想买",
    "下定",
    "订车",
    "试驾",
    "置换",
    "冲",
    "马上买",
]

MID_INTENT_HINTS = [
    "想参与",
    "想要",
    "好想",
    "期待",
    "关注",
    "想了解",
    "想看",
]

KEYWORD_PATTERNS = {
    "价格": ["价格", "太贵", "便宜", "权益"],
    "智驾": ["智驾", "辅助驾驶", "自动驾驶"],
    "续航": ["续航", "电池", "充电", "快充", "800v"],
    "座舱": ["座舱", "内饰", "车机"],
    "空间": ["空间", "后排", "储物"],
    "安全": ["安全", "刹车", "碰撞"],
    "性能": ["性能", "加速", "底盘"],
    "机器人": ["机器人", "人形", "仿生"],
    "工厂": ["工厂", "产线", "流水线", "制造"],
    "就业": ["就业", "岗位", "打螺丝", "基层"],
    "成本": ["成本", "便宜", "贵"],
    "规模化": ["规模化", "部署", "普及"],
    "决策": ["决策", "自主", "智能"],
}

STOPWORDS = {
    "我们",
    "他们",
    "这个",
    "那个",
    "现在",
    "就是",
    "一个",
    "一下",
    "真的",
    "感觉",
    "有点",
    "应该",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="回填 danmaku_analysis 的情感、意向和关键词")
    parser.add_argument("--task-id", type=int, help="仅处理指定 task_id")
    parser.add_argument("--event-id", type=str, help="仅处理指定 SIM 场次 event_id 关联的任务")
    parser.add_argument("--all", action="store_true", help="处理所有弹幕")
    parser.add_argument("--force", action="store_true", help="覆盖已有分析结果")
    return parser.parse_args()


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def extract_keywords(content: str) -> list[str]:
    matched: list[str] = []
    lowered = content.lower()
    for canonical, phrases in KEYWORD_PATTERNS.items():
        if any(phrase.lower() in lowered for phrase in phrases):
            matched.append(canonical)

    if matched:
        return matched[:5]

    tokens = []
    for token in re.findall(r"[A-Za-z0-9]{2,16}|[\u4e00-\u9fff]{2,6}", content):
        normalized = token.strip().lower()
        if len(normalized) < 2:
            continue
        if normalized in STOPWORDS:
            continue
        tokens.append(normalized)

    deduped: list[str] = []
    for token in tokens:
        if token not in deduped:
            deduped.append(token)
    return deduped[:5]


def score_sentiment(content: str) -> float:
    text = content.lower()
    pos = sum(1 for hint in POSITIVE_HINTS if hint.lower() in text)
    neg = sum(1 for hint in NEGATIVE_HINTS if hint.lower() in text)
    if pos == 0 and neg == 0:
        return 0.0
    return round(clamp((pos - neg) / max(pos + neg, 1), -1.0, 1.0), 2)


def score_intent(content: str) -> float | None:
    text = content.lower()
    if any(hint.lower() in text for hint in HIGH_INTENT_HINTS):
        return 8.5
    if any(hint.lower() in text for hint in MID_INTENT_HINTS):
        return 6.0
    return None


def resolve_task_ids(db, args: argparse.Namespace) -> list[int] | None:
    """返回需处理的 task_id 列表；None 表示不过滤 task_id。"""
    if args.task_id is not None:
        return [args.task_id]
    if args.event_id:
        rows = (
            db.query(EventTask.id)
            .filter(EventTask.event_id == args.event_id)
            .order_by(EventTask.id.asc())
            .all()
        )
        task_ids = [row[0] for row in rows]
        if not task_ids:
            print(f"未找到 event_id={args.event_id} 的直播任务", file=sys.stderr)
        return task_ids
    if args.all:
        return None
    return []


def main() -> int:
    args = parse_args()
    if not args.all and args.task_id is None and not args.event_id:
        print(
            "请使用 --task-id、--event-id 指定范围，或使用 --all 处理全部弹幕。",
            file=sys.stderr,
        )
        return 1

    db = SessionLocal()
    try:
        task_ids = resolve_task_ids(db, args)
        if task_ids is not None and len(task_ids) == 0:
            return 0

        query = db.query(DanmakuRecord)
        if task_ids is not None:
            query = query.filter(DanmakuRecord.task_id.in_(task_ids))

        records = query.order_by(DanmakuRecord.id.asc()).all()
        processed = 0
        created = 0
        updated = 0

        for record in records:
            processed += 1
            analysis = (
                db.query(DanmakuAnalysis)
                .filter(DanmakuAnalysis.danmaku_id == record.id)
                .first()
            )
            if analysis and not args.force:
                continue

            content = (record.content or "").strip()
            if not content:
                continue

            sentiment_score = score_sentiment(content)
            intent_score = score_intent(content)
            keywords = extract_keywords(content)

            if analysis is None:
                analysis = DanmakuAnalysis(
                    danmaku_id=record.id,
                    task_id=record.task_id,
                )
                db.add(analysis)
                created += 1
            else:
                updated += 1

            analysis.sentiment_score = sentiment_score
            analysis.intent_score = intent_score
            analysis.keywords = keywords

            if processed % 200 == 0:
                db.commit()

        db.commit()
        print(
            f"回填完成: processed={processed}, created={created}, updated={updated}"
        )
        return 0
    except Exception as exc:
        db.rollback()
        print(f"回填失败: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
