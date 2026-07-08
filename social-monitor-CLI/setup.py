from setuptools import find_packages, setup

from social_monitor.__version__ import __version__

setup(
    name="social-monitor",
    version=__version__,
    description="轻量级社交媒体监控命令行工具",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "click>=8.0.0",
        "httpx>=0.24.0",
        "feedparser>=6.0.0",
        "PyYAML>=6.0",
    ],
    extras_require={
        "postgres": ["psycopg2-binary>=2.9.0"],
        "mysql": ["pymysql>=1.0.0"],
        "browser": ["playwright>=1.30.0"],
        "live": ["websockets>=12.0", "brotli>=1.0.0"],
    },
    entry_points={
        "console_scripts": [
            "social-monitor=social_monitor.cli:main",
        ],
    },
)
