import os
from pathlib import Path
from typing import Optional

import yaml

from social_monitor.utils.logger import setup_logger

logger = setup_logger(__name__)

CONFIG_DIR = Path.home() / ".social-monitor"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
MONITOR_FILE = CONFIG_DIR / "monitor.yaml"
COOKIE_DIR = CONFIG_DIR / "cookies"
BROWSER_DIR = CONFIG_DIR / "browser"
LIVE_STATE_DIR = CONFIG_DIR / "live_state"

ENV_VAR_MAP = {
    "weibo": "SM_WEIBO_COOKIE",
    "xiaohongshu": "SM_XIAOHONGSHU_COOKIE",
    "douyin": "SM_DOUYIN_COOKIE",
    "zhihu": "SM_ZHIHU_COOKIE",
}

COOKIE_PLATFORMS = frozenset(ENV_VAR_MAP.keys())


def load_config() -> dict:
    """加载用户配置"""
    if not CONFIG_FILE.exists():
        return {}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def mask_cookie(cookie: str) -> str:
    """日志脱敏"""
    if not cookie:
        return "(empty)"
    if len(cookie) <= 16:
        return "***"
    return f"{cookie[:8]}...{cookie[-4:]}"


def get_cookie_file(platform: str) -> Path:
    return COOKIE_DIR / f"{platform}.txt"


def get_browser_dir(platform: str) -> Path:
    return BROWSER_DIR / platform


def has_browser_session(platform: str) -> bool:
    """是否已有 Playwright 持久化登录态"""
    browser_dir = get_browser_dir(platform)
    return browser_dir.exists() and any(browser_dir.iterdir())


def save_cookie(platform: str, cookie: str) -> Path:
    """保存 Cookie 到独立文件（权限 600）"""
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    cookie_file = get_cookie_file(platform)
    cookie_file.write_text(cookie.strip(), encoding="utf-8")
    os.chmod(cookie_file, 0o600)
    logger.info("Cookie 已保存 platform=%s file=%s value=%s", platform, cookie_file, mask_cookie(cookie))
    return cookie_file


def get_cookie(platform: str, override: Optional[str] = None) -> Optional[str]:
    """获取 Cookie，优先级：CLI > 环境变量 > cookie 文件 > config.yaml"""
    if override:
        return override.strip()

    env_key = ENV_VAR_MAP.get(platform)
    if env_key:
        env_val = os.environ.get(env_key)
        if env_val:
            logger.debug("使用环境变量 Cookie platform=%s %s", platform, mask_cookie(env_val))
            return env_val.strip()

    cookie_file = get_cookie_file(platform)
    if cookie_file.exists():
        value = cookie_file.read_text(encoding="utf-8").strip()
        if value:
            logger.debug("使用文件 Cookie platform=%s file=%s", platform, cookie_file)
            return value

    config = load_config()
    platform_cfg = config.get(platform, {})
    if isinstance(platform_cfg, dict):
        cfg_cookie = platform_cfg.get("cookie")
        if cfg_cookie:
            logger.debug("使用配置 Cookie platform=%s %s", platform, mask_cookie(cfg_cookie))
            return cfg_cookie.strip()

    return None


def get_cookie_source(platform: str, override: Optional[str] = None) -> str:
    """返回 Cookie 来源，便于 check 输出"""
    if override:
        return "cli"
    env_key = ENV_VAR_MAP.get(platform, "")
    if env_key and os.environ.get(env_key):
        return f"env:{env_key}"
    if get_cookie_file(platform).exists():
        return f"file:{get_cookie_file(platform)}"
    config = load_config()
    if isinstance(config.get(platform), dict) and config[platform].get("cookie"):
        return f"config:{CONFIG_FILE}"
    if has_browser_session(platform):
        return f"browser:{get_browser_dir(platform)}"
    return "none"
