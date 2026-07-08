from pathlib import Path

import yaml

from social_monitor.utils.cookie_manager import CONFIG_DIR, CONFIG_FILE, load_config

DEFAULT_CONFIG = {
    "weibo": {"cookie": ""},
    "xiaohongshu": {"cookie": ""},
    "douyin": {"cookie": ""},
    "zhihu": {"cookie": ""},
    "rsshub_url": "http://localhost:1200",
    "feishu_webhook": "",
    "redis": {
        "host": "localhost",
        "port": 6379,
        "db": 0,
    },
    "storage": {
        "type": "postgres",
        "data_dir": str(Path.home() / ".social-monitor" / "data"),
    },
    "postgres": {
        "host": "localhost",
        "port": 5432,
        "user": "postgres",
        "password": "postgres",
        "database": "social_monitor",
    },
    "mysql": {
        "host": "localhost",
        "port": 3306,
        "user": "root",
        "password": "",
        "database": "social_monitor",
    },
    "rate_limit": {
        "mode": "safe",
        "min_interval": 10,
        "max_interval": 20,
        "daily_max_requests": 80,
        "stop_on_403": True,
    },
    "monitor": {
        "feishu_on_diff": True,
        "skip_on_check_fail": True,
    },
}


def init_config() -> Path:
    """初始化配置文件"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.dump(DEFAULT_CONFIG, f, allow_unicode=True, default_flow_style=False)
    return CONFIG_FILE


def get_rsshub_url(override: str = None) -> str:
    if override:
        return override.rstrip("/")
    config = load_config()
    return config.get("rsshub_url", "http://localhost:1200").rstrip("/")


def get_monitor_settings() -> dict:
    config = load_config()
    return config.get("monitor") or DEFAULT_CONFIG.get("monitor", {})


def init_monitor_config(source: Path = None) -> Path:
    """从项目 monitor.yaml.example 复制监控清单"""
    from social_monitor.utils.cookie_manager import CONFIG_DIR, MONITOR_FILE

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if MONITOR_FILE.exists():
        return MONITOR_FILE
    if source is None:
        source = Path(__file__).resolve().parent.parent / "monitor.yaml.example"
    if source.exists():
        MONITOR_FILE.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        MONITOR_FILE.write_text("weibo:\n  accounts: []\n", encoding="utf-8")
    return MONITOR_FILE
