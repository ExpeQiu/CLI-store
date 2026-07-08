"""CLI 异常定义"""


class ClautoError(Exception):
    """基础异常"""


class ScrapeError(ClautoError):
    """抓取失败"""


class ConfigError(ClautoError):
    """配置缺失或无效"""
