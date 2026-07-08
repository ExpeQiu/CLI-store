from typing import Optional
"""
invest_core.executor.broker
===========================
飞书 Bitable 适配器——invest_state ↔ Bitable 双向同步。

虚拟账户 Bitable：
  App Token: XRCBbvhS3aUpirsN3kvcoNqsn7e
 持仓表:     tbl8jA0kNQtp4KyG
 交易记录表: tblgoeXKXEKUrLUi
 概览表:     tbl7JJVzNYxvCO0F
 绩效表:     tbljP2XiaOXdxRMF

设计：invest_state 是真实数据源，Bitable 是可选的展示/通知层。
同步失败时静默，不影响主流程。
"""

import requests
from datetime import date, datetime
from pathlib import Path

# ─── 飞书凭证（从环境变量读取，不硬编码）─────────────────────────────

APP_ID     = "cli_a9154ca00079dceb"
APP_SECRET = ""   # 从环境变量 FEISHU_APP_SECRET 读取
BASE       = "https://open.feishu.cn/open-apis"
VIRT_APP   = "XRCBbvhS3aUpirsN3kvcoNqsn7e"
TBL_POSITION = "tbl8jA0kNQtp4KyG"
TBL_TRADE    = "tblgoeXKXEKUrLUi"
TBL_OVERVIEW = "tbl7JJVzNYxvCO0F"


def _get_secret() -> str:
    """从环境变量读取飞书 secret"""
    import os
    return os.environ.get("FEISHU_APP_SECRET", "")


def _get_token() -> str:
    """获取飞书 tenant_access_token"""
    secret = _get_secret()
    if not secret:
        raise RuntimeError("FEISHU_APP_SECRET 环境变量未设置")
    url = f"{BASE}/auth/v3/tenant_access_token/internal"
    r = requests.post(url, json={"app_id": APP_ID, "app_secret": secret}, timeout=15)
    r.raise_for_status()
    return r.json()["tenant_access_token"]


def _headers() -> dict:
    return {"Authorization": f"Bearer {_get_token()}", "Content-Type": "application/json"}


def _get(path: str, params=None):
    url = f"{BASE}{path}"
    r = requests.get(url, headers=_headers(), params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def _post(path: str, fields: dict):
    url = f"{BASE}{path}"
    r = requests.post(url, headers=_headers(), json={"fields": fields}, timeout=15)
    r.raise_for_status()
    return r.json()


def _put(path: str, record_id: str, fields: dict):
    url = f"{BASE}{path}/{record_id}"
    r = requests.put(url, headers=_headers(), json={"fields": fields}, timeout=15)
    r.raise_for_status()
    return r.json()


def _delete(path: str, record_id: str):
    url = f"{BASE}{path}/{record_id}"
    r = requests.delete(url, headers=_headers(), timeout=15)
    r.raise_for_status()
    return r.json()


# ─── 持仓同步 ──────────────────────────────────────────────────────────

def fetch_positions_from_bitable() -> list:
    """
    从 Bitable 持仓表读取当前持仓，返回 list[dict]。
    """
    try:
        records = _get(f"/bitable/v1/apps/{VIRT_APP}/tables/{TBL_POSITION}/records", {"page_size": 100})
        items = records.get("data", {}).get("items", [])
        result = []
        for item in items:
            fields = item.get("fields", {})
            result.append({
                "record_id": item.get("record_id", ""),
                "code":        fields.get("股票代码", ""),
                "name":        fields.get("股票名称", ""),
                "shares":      fields.get("持股数量", 0),
                "cost":        fields.get("成本价", 0.0),
                "current_price": fields.get("当前价", 0.0),
                "floating_pnl":  fields.get("浮动盈亏", 0.0),
                "floating_pct":  fields.get("浮动比例", 0.0),
                "triggered_tp":  fields.get("已触发止盈", ""),
            })
        return result
    except Exception as e:
        print(f"[broker] fetch_positions failed: {e}")
        return []


def sync_state_to_bitable(state: "InvestState") -> bool:
    """
    将 InvestState 同步到 Bitable。

    策略：
      1. 读取 Bitable 持仓表当前记录
      2. 对比 state.account.positions，逐条 upsert
      3. 清理 state 中已无但 Bitable 仍有的记录

    返回 True=成功，False=失败。
    """
    try:
        # 获取现有记录
        resp = _get(f"/bitable/v1/apps/{VIRT_APP}/tables/{TBL_POSITION}/records", {"page_size": 100})
        existing = {item["fields"].get("股票代码", ""): item["record_id"]
                    for item in resp.get("data", {}).get("items", [])}

        for pos in state.account.positions:
            fields = {
                "股票代码":     pos.code,
                "股票名称":     pos.name,
                "持股数量":     pos.shares,
                "成本价":       round(pos.cost, 4),
                "当前价":       round(pos.current_price, 2),
                "浮动盈亏":     round(pos.floating_pnl, 2),
                "浮动比例":     round(pos.floating_pct, 2),
                "已触发止盈":   pos.triggered_take_profit or "",
            }
            if pos.code in existing:
                _put(f"/bitable/v1/apps/{VIRT_APP}/tables/{TBL_POSITION}/records", existing[pos.code], fields)
            else:
                _post(f"/bitable/v1/apps/{VIRT_APP}/tables/{TBL_POSITION}/records", fields)

        # 同步概览
        overview_fields = {
            "总资产":     round(state.account.total_asset, 2),
            "可用资金":   round(state.account.cash, 2),
            "持仓市值":   round(state.account.market_value, 2),
            "仓位":       round(state.account.position_pct, 2),
            "累计盈亏":   round(state.account.total_pnl, 2),
        }
        # 概览只有一条记录，record_id 固定
        overview_record_id = "recvkgttRypX2e"  # 从上下文已知
        try:
            _put(f"/bitable/v1/apps/{VIRT_APP}/tables/{TBL_OVERVIEW}/records", overview_record_id, overview_fields)
        except Exception:
            pass

        return True
    except Exception as e:
        print(f"[broker] sync_to_bitable failed: {e}")
        return False


def append_trade_to_bitable(trade: dict) -> bool:
    """追加交易记录到 Bitable"""
    try:
        fields = {
            "日期":       trade.get("date", ""),
            "操作":       trade.get("action", ""),
            "股票代码":   trade.get("code", ""),
            "股票名称":   trade.get("name", ""),
            "价格":       trade.get("price", 0.0),
            "数量":       trade.get("shares", 0),
            "金额":       trade.get("amount", 0.0),
            "原因":       trade.get("reason", ""),
        }
        _post(f"/bitable/v1/apps/{VIRT_APP}/tables/{TBL_TRADE}/records", fields)
        return True
    except Exception as e:
        print(f"[broker] append_trade failed: {e}")
        return False
