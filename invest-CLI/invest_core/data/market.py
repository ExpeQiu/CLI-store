"""
invest_core.data.market
=======================
行情数据获取层。

提供：
  - K线数据（新浪历史K线）
  - RSI计算（Wilder平滑）
  - 指数技术指标（上证、深证、创业板）
  - 个股技术指标（RSI/MA/ATR/量比）
  - 腾讯实时行情（价格/涨跌幅）

设计原则：纯函数，无副作用。
"""

from datetime import datetime, timedelta
from typing import Optional
import json
import ssl
import urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"

# ─── 缓存（与 macro.py 同样的 JSON 文件模式）───────────────────────────────────

CACHE_DIR = Path.home() / ".hermes" / "data" / "invest" / "market_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL = timedelta(hours=4)  # K 线/技术指标，4h 够用

# 失败标记短期缓存
FAIL_TTL = timedelta(minutes=10)


def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def _cache_get(key: str, ttl: timedelta = CACHE_TTL) -> Optional[dict]:
    p = _cache_path(key)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if datetime.now() - datetime.fromisoformat(data["cached_at"]) > ttl:
            return None
        return data["payload"]
    except Exception:
        return None


def _cache_put(key: str, payload: dict) -> None:
    try:
        _cache_path(key).write_text(
            json.dumps({"cached_at": datetime.now().isoformat(), "payload": payload},
                       ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    except Exception:
        pass


# ─── HTTP 工具 ───────────────────────────────────────────────────────────────

def _get(url: str, headers: dict = None, timeout: int = 5) -> Optional[bytes]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA, **(headers or {})})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.read()
    except Exception:
        return None


# ─── K线获取 ───────────────────────────────────────────────────────────────

def fetch_sina_kline(symbol: str, datalen: int = 90) -> list[dict]:
    """
    获取新浪历史K线数据（带缓存 + 失败标记）。

    Args:
        symbol: 新浪格式代码，如 sh000001（上证）、sz399001（深证）、sz000988（华工）
        datalen: 拉取天数

    Returns:
        list[dict]，每项含：day, open, close, high, low, volume（latest first）
        出错返回空列表（优先用 stale 缓存兜底）。
    """
    cache_key = f"sina_kline_{symbol}_{datalen}"

    # 1. 缓存命中
    cached = _cache_get(cache_key)
    if cached is not None and isinstance(cached, list):
        return cached

    # 2. 短期失败标记（10 分钟内尝试过且失败）
    fail_marker = _cache_get(f"_failed_{cache_key}", ttl=FAIL_TTL)
    if fail_marker is not None:
        # 用 stale 兜底
        p = _cache_path(cache_key)
        if p.exists():
            try:
                stale = json.loads(p.read_text(encoding="utf-8")).get("payload")
                if isinstance(stale, list):
                    return stale
            except Exception:
                pass
        return []

    # 3. 实际抓取
    url = (
        f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php"
        f"/CN_MarketData.getKLineData?symbol={symbol}&scale=240&ma=5&datalen={datalen}"
    )
    data = _get(url, timeout=5)
    if not data:
        _cache_put(f"_failed_{cache_key}", {"at": datetime.now().isoformat()})
        # stale 兜底
        p = _cache_path(cache_key)
        if p.exists():
            try:
                stale = json.loads(p.read_text(encoding="utf-8")).get("payload")
                if isinstance(stale, list):
                    return stale
            except Exception:
                pass
        return []
    try:
        klines = json.loads(data)
        result = []
        for k in klines:
            result.append({
                "day": k["day"],
                "open": float(k["open"]),
                "close": float(k["close"]),
                "high": float(k["high"]),
                "low": float(k["low"]),
                "volume": float(k["volume"]),
            })
        if result:
            _cache_put(cache_key, result)
        return result
    except Exception:
        return []


# ─── RSI 计算 ──────────────────────────────────────────────────────────────

def wilder_rsi(closes: list[float], period: int = 14) -> float:
    """
    Wilder RSI 计算。

    Args:
        closes: 价格列表（latest first）
        period: RSI周期，默认14

    Returns:
        RSI 值 0~100，精度2位小数。
        数据不足返回 50.0。
    """
    if len(closes) < period + 1:
        return 50.0

    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 2)


# ─── ATR 计算 ──────────────────────────────────────────────────────────────

def calc_atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float:
    """
    ATR（Average True Range）计算。

    Args:
        highs/lows/closes: 价格列表（latest first）
        period: ATR周期，默认14

    Returns:
        ATR 值，精度3位小数。
    """
    if len(closes) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(closes)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        trs.append(max(hl, hc, lc))
    if len(trs) < period:
        return 0.0
    return round(sum(trs[-period:]) / period, 3)


# ─── 代码转换 ──────────────────────────────────────────────────────────────

def stock_code_to_sina(code: str) -> str:
    """股票代码 → 新浪格式"""
    code = code.strip().zfill(6)
    if code.startswith(("0", "3")):
        return f"sz{code}"   # 深交所
    elif code.startswith(("6", "9")) or code in ("000001",):
        return f"sh{code}"   # 上交所
    elif code.startswith(("5", "1")):
        return f"sh{code}"   # ETF/指数
    return f"sh{code}"


def stock_code_to_tencent(code: str) -> str:
    """股票代码 → 腾讯格式"""
    code = code.strip().zfill(6)
    if code.startswith(("6", "9")):
        return f"sh{code}"
    elif code.startswith(("8",)):
        return f"bj{code}"
    else:
        return f"sz{code}"


# ─── 腾讯实时行情 ─────────────────────────────────────────────────────────

def tencent_quote(codes: list[str]) -> dict[str, dict]:
    """
    腾讯实时行情批量获取。

    Args:
        codes: 股票代码列表，如 ["000988", "601138", "sh000001"]

    Returns:
        dict[code, {name, price, change_pct, volume, ...}]
        code 为原始代码（非前缀格式）。
    """
    if not codes:
        return {}

    # 转换格式
    prefixed = []
    for c in codes:
        c = str(c).zfill(6)
        if c.startswith(("6", "9")):
            prefixed.append(f"sh{c}")
        elif c.startswith("8"):
            prefixed.append(f"bj{c}")
        else:
            prefixed.append(f"sz{c}")

    url = f"https://qt.gtimg.cn/q={','.join(prefixed)}"
    data = _get(url, timeout=10)
    if not data:
        return {}

    try:
        text = data.decode("gbk")
    except Exception:
        return {}

    result = {}
    for line in text.strip().split(";"):
        if "=" not in line or '"' not in line:
            continue
        raw_key = line.split("=")[0].split("_")[-1]
        parts = line.split('"')[1].split("~")
        if len(parts) < 10:
            continue

        # 解析原始代码（去掉前缀）
        key = raw_key
        if key.startswith("sh") or key.startswith("sz") or key.startswith("bj"):
            key = key[2:]

        result[key] = {
            "name": parts[1],
            "price": float(parts[3]) if parts[3] else 0.0,
            "change_pct": float(parts[32]) if len(parts) > 32 and parts[32] else 0.0,
            "volume": float(parts[36]) if len(parts) > 36 and parts[36] else 0.0,  # 手
            "amount": float(parts[37]) if len(parts) > 37 and parts[37] else 0.0,  # 元
            "open": float(parts[5]) if len(parts) > 5 and parts[5] else 0.0,
            "high": float(parts[33]) if len(parts) > 33 and parts[33] else 0.0,
            "low": float(parts[34]) if len(parts) > 34 and parts[34] else 0.0,
            "prev_close": float(parts[4]) if len(parts) > 4 and parts[4] else 0.0,
        }
    return result


# ─── 指数技术指标 ────────────────────────────────────────────────────────

def fetch_index_tech(code: str = "sh000001") -> dict:
    """
    获取大盘指数（上证/深证/创业板）的技术指标。

    Args:
        code: 新浪格式指数代码，默认 sh000001（上证）

    Returns:
        dict: {ok, code, name, price, change_pct, rsi14, ma5, ma20, ma60,
               ma5_dir, ma20_dir, ma60_dir, atr14, above_ma20, updated_at}
    """
    klines = fetch_sina_kline(code, datalen=80)
    if not klines or len(klines) < 20:
        return {"ok": False, "code": code}

    closes = [k["close"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]

    price = closes[0]
    prev_close = closes[1] if len(closes) > 1 else price
    change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0.0

    rsi14 = wilder_rsi(closes, 14)
    atr14 = calc_atr(highs, lows, closes, 14)

    ma5 = round(sum(closes[:5]) / 5, 3)
    ma20 = round(sum(closes[:20]) / 20, 3) if len(closes) >= 20 else ma5
    ma60 = round(sum(closes[:60]) / 60, 3) if len(closes) >= 60 else ma20

    # MA方向（前5天均值 vs 前6~10天均值）
    ma5_prev = sum(closes[5:10]) / 5 if len(closes) >= 10 else sum(closes[5:]) / max(len(closes) - 5, 1)
    ma20_prev = sum(closes[20:25]) / 5 if len(closes) >= 25 else sum(closes[20:]) / max(len(closes) - 20, 1)

    ma5_dir = 1 if ma5 > ma5_prev * 1.001 else -1 if ma5 < ma5_prev * 0.999 else 0
    ma20_dir = 1 if ma20 > ma20_prev * 1.001 else -1 if ma20 < ma20_prev * 0.999 else 0

    name_map = {
        "sh000001": "上证指数",
        "sz399001": "深证成指",
        "sz399006": "创业板指",
    }

    return {
        "ok": True,
        "code": code,
        "name": name_map.get(code, code),
        "price": price,
        "change_pct": change_pct,
        "rsi14": rsi14,
        "ma5": ma5,
        "ma20": ma20,
        "ma60": ma60,
        "ma5_dir": ma5_dir,
        "ma20_dir": ma20_dir,
        "atr14": atr14,
        "above_ma20": price > ma20,
        "above_ma5": price > ma5,
        "updated_at": datetime.now().isoformat(),
    }


# ─── 个股技术指标 ─────────────────────────────────────────────────────────

def fetch_stock_tech(code: str) -> dict:
    """
    获取个股技术指标：RSI、均线、ATR、成交量比。

    Args:
        code: 6位股票代码

    Returns:
        dict: {ok, code, name, price, change_pct, rsi14, ma5, ma20, atr14,
               vol_ratio, ma5_dir, ma20_dir, above_ma20, above_ma5, updated_at}
    """
    sina_code = stock_code_to_sina(code)
    klines = fetch_sina_kline(sina_code, datalen=80)
    if not klines or len(klines) < 20:
        return {"ok": False, "code": code}

    closes = [k["close"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]
    volumes = [k["volume"] for k in klines]

    price = closes[0]
    prev_close = closes[1] if len(closes) > 1 else price
    change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0.0

    rsi14 = wilder_rsi(closes, 14)
    atr14 = calc_atr(highs, lows, closes, 14)

    ma5 = round(sum(closes[:5]) / 5, 3)
    ma20 = round(sum(closes[:20]) / 20, 3) if len(closes) >= 20 else ma5

    vol20 = sum(volumes[:20]) / 20 if len(volumes) >= 20 else sum(volumes) / max(len(volumes), 1)
    vol_ratio = round(volumes[0] / vol20, 2) if vol20 > 0 else 1.0

    # MA方向
    ma5_prev = sum(closes[5:10]) / 5 if len(closes) >= 10 else sum(closes[5:]) / max(len(closes) - 5, 1)
    ma20_prev = sum(closes[20:25]) / 5 if len(closes) >= 25 else sum(closes[20:]) / max(len(closes) - 20, 1)
    ma5_dir = 1 if ma5 > ma5_prev * 1.001 else -1 if ma5 < ma5_prev * 0.999 else 0
    ma20_dir = 1 if ma20 > ma20_prev * 1.001 else -1 if ma20 < ma20_prev * 0.999 else 0

    # 腾讯行情获取名称
    quote = tencent_quote([code])
    name = quote.get(code, {}).get("name", code)

    return {
        "ok": True,
        "code": code,
        "name": name,
        "price": price,
        "change_pct": change_pct,
        "rsi14": rsi14,
        "ma5": ma5,
        "ma20": ma20,
        "atr14": atr14,
        "vol_ratio": vol_ratio,
        "ma5_dir": ma5_dir,
        "ma20_dir": ma20_dir,
        "above_ma20": price > ma20,
        "above_ma5": price > ma5,
        "updated_at": datetime.now().isoformat(),
    }


# ─── 聚合：fetch_all_index_tech ────────────────────────────────────────────

def fetch_all_index_tech() -> dict[str, dict]:
    """
    获取上证、深证、创业板三大指数的技术指标（并行抓取）。

    实测：串行 6.5s → 并行 ~2s（取决于最慢的单个接口）。
    """
    indices = {
        "sh000001": "上证指数",
        "sz399001": "深证成指",
        "sz399006": "创业板指",
    }

    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(fetch_index_tech, code): code for code in indices}
        result = {}
        for fut in as_completed(futures, timeout=15):
            code = futures[fut]
            try:
                result[code] = fut.result(timeout=12)
            except Exception as e:
                result[code] = {"symbol": code, "ok": False,
                                "error": str(e)[:100],
                                "updated_at": datetime.now().isoformat()}
    return result
