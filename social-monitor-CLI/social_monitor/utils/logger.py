import logging
import sys


def setup_logger(name: str = "social-monitor", level: int = logging.INFO) -> logging.Logger:
    """配置并返回 logger"""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    if name != "social-monitor":
        logger.propagate = False
    return logger
