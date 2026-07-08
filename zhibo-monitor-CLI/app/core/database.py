from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import declarative_base, sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

# 从环境变量获取数据库连接，如果不存在则使用本地 PostgreSQL (可替换为 SQLite 以方便测试)
# postgresql://user:password@localhost/zhibo_monitor
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _prepare_database_url(raw_url: str) -> str:
    url: URL = make_url(raw_url)
    if url.drivername != "sqlite" or not url.database or url.database == ":memory:":
        return raw_url

    db_path = Path(url.database)
    if not db_path.is_absolute():
        db_path = (PROJECT_ROOT / db_path).resolve()

    db_path.parent.mkdir(parents=True, exist_ok=True)
    return url.set(database=str(db_path)).render_as_string(hide_password=False)


DATABASE_URL = _prepare_database_url(
    os.getenv("DATABASE_URL", "sqlite:///./zhibo_monitor.db")
)

engine = create_engine(
    DATABASE_URL, 
    # SQLite special config
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
