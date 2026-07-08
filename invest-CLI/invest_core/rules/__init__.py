from typing import Optional
"""
invest_core.rules
================
规则解析层。

当前实现：RuleSet defaults = 规则真相来源（与 invest_rules.md v2.3 同步）。
未来可选：invest_rules.md → RuleSet 的正式解析器，用于规则变更时自动校验。

invest_rules.md 是人类可读的规范文档，
RuleSet Pydantic 模型是代码执行的契约。
两者通过本模块关联。
"""

from pathlib import Path
from invest_core.types import RuleSet

# ─── 规则文件路径 ────────────────────────────────────────────────────────────

RULES_MD = Path.home() / ".hermes" / "invest_rules.md"
RULES_CACHE = Path.home() / ".hermes" / "invest_core" / "rules_cache.json"


# ─── 加载规则 ────────────────────────────────────────────────────────────────

def load_rules() -> RuleSet:
    """
    加载当前规则集。

    优先从缓存加载（快速），缓存不存在则返回默认 RuleSet
    （其默认值已与 invest_rules.md v2.3 同步）。

    未来可扩展：对 invest_rules.md 做运行时解析 + 缓存校验。
    """
    if RULES_CACHE.exists():
        try:
            import json
            data = json.loads(RULES_CACHE.read_text())
            return RuleSet.model_validate(data)
        except Exception:
            pass
    # 默认值（与 invest_rules.md v2.3 同步）
    return RuleSet()


def save_rules_cache(rules: RuleSet) -> None:
    """保存规则缓存（用于加速）"""
    import json
    RULES_CACHE.parent.mkdir(parents=True, exist_ok=True)
    RULES_CACHE.write_text(json.dumps(rules.model_dump(), ensure_ascii=False, indent=2))


# ─── 规则校验（可选）───────────────────────────────────────────────────────────

def validate_rules_md() -> bool:
    """
    可选：校验 invest_rules.md 与 RuleSet 默认值的一致性。
    用于规则更新后人工核对，避免两者漂移。

    当前为空实现（v2.3 手工同步完成）。
    """
    return True
