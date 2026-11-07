"""저장소. 클라우드는 Supabase 의 overseas 스키마, 이 PC 시험은 SQLite 파일."""
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import (JSON, BigInteger, Boolean, Column, DateTime, Float, Index, Integer, MetaData,
                        String, Table, Text, UniqueConstraint, create_engine, func, select, update)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine

from core import config

SCHEMA = "overseas"
meta = MetaData(schema=SCHEMA)
Id = BigInteger().with_variant(Integer, "sqlite")  # SQLite 는 INTEGER 여야 자동 번호
Json = JSON().with_variant(JSONB, "postgresql")
Ts = DateTime(timezone=True)

watchlist = Table(
    "watchlist", meta,
    Column("ticker", String(16), primary_key=True),
    Column("country", String(4), nullable=False, server_default="US"),
    Column("name", String(200)),
    Column("cik", Integer),
    Column("keywords", String(300)),   # 유튜브 영상 찾을 때 쓰는 이름 (쉼표로 구분)
    Column("memo", Text),
    Column("active", Boolean, nullable=False, server_default="1"),
    Column("added_at", Ts),
)

items = Table(
    "items", meta,
    Column("id", Id, primary_key=True, autoincrement=True),
    Column("ticker", String(16), nullable=False),
    Column("kind", String(16), nullable=False),      # filing, earnings, insider, ownership, news, analysis, grade, video
    Column("source", String(40), nullable=False),    # 가져온 곳 (sec, yahoo, google, ...)
    Column("publisher", String(80)),                 # 실제 작성한 곳 (Reuters, Motley Fool, ...)
    Column("tier", String(16)),                      # 1차 자료, 주요 언론, 분석·의견, ...
    Column("title", Text, nullable=False),
    Column("title_ko", Text),
    Column("url", Text),
    Column("published_at", Ts),
    Column("fetched_at", Ts, nullable=False),
    Column("is_initial", Boolean, nullable=False, server_default="0"),  # 종목 첫 등록 때 받은 과거 자료
    Column("uid", String(200), nullable=False),      # 중복 확인용
    Column("extra", Json),
    UniqueConstraint("ticker", "uid", name="items_ticker_uid"),
    Index("items_ticker_published", "ticker", "published_at"),
)

fetch_log = Table(
    "fetch_log", meta,
    Column("id", Id, primary_key=True, autoincrement=True),
    Column("run_at", Ts, nullable=False),
    Column("ticker", String(16)),
    Column("source", String(40), nullable=False),
    Column("status", String(8), nullable=False),     # ok / error
    Column("found", Integer),
    Column("added", Integer),
    Column("seconds", Float),
    Column("message", Text),
)

channels = Table(
    "channels", meta,
    Column("channel_id", String(40), primary_key=True),
    Column("name", String(100)),
    Column("active", Boolean, nullable=False, server_default="1"),
)

# 3단계(요약·번역)에서 사용
ai_results = Table(
    "ai_results", meta,
    Column("id", Id, primary_key=True, autoincrement=True),
    Column("item_id", BigInteger, nullable=False),
    Column("kind", String(32), nullable=False),      # summary, translation, section:...
    Column("model", String(60), nullable=False),
    Column("content", Text),
    Column("input_tokens", Integer),
    Column("output_tokens", Integer),
    Column("cost_usd", Float),
    Column("created_at", Ts),
    UniqueConstraint("item_id", "kind", "model", name="ai_results_item_kind_model"),
)

settings = Table(
    "settings", meta,
    Column("key", String(60), primary_key=True),
    Column("value", Text),
)

DEFAULT_CHANNELS = [
    ("UCrp_UI8XtuYfpiqluWLD7Lw", "CNBC Television"),
    ("UCvJJ_dzjViJCoLf5uKUTwoA", "CNBC"),
    ("UCIALMKvObZNtJ6AmdCLP7Lg", "Bloomberg Television"),
    ("UCEAZeUIeJs0IjQiqTCdVSIg", "Yahoo Finance"),
    ("UCK7tptUDHh-RYDsdxO1-5QQ", "The Wall Street Journal"),
]

_engine: Engine | None = None


def now() -> datetime:
    return datetime.now(timezone.utc)


def database_url() -> str | None:
    url = config.get("OVERSEAS_DATABASE_URL")
    if url:
        return url
    if config.is_local():
        return f"sqlite:///{(config.ROOT / 'data' / 'overseas.db').as_posix()}"
    return None


def engine() -> Engine:
    global _engine
    if _engine is None:
        url = database_url()
        if url is None:
            raise RuntimeError("OVERSEAS_DATABASE_URL 이 설정되지 않았습니다")
        if url.startswith("sqlite"):
            (config.ROOT / "data").mkdir(exist_ok=True)
            _engine = create_engine(url, execution_options={"schema_translate_map": {SCHEMA: None}})
        else:
            url = url.replace("postgres://", "postgresql://", 1).replace("postgresql://", "postgresql+psycopg://", 1)
            # Supabase 연결 중계(pooler)는 prepared statement 를 지원하지 않는다
            _engine = create_engine(url, pool_pre_ping=True, connect_args={"prepare_threshold": None})
    return _engine


def init_db():
    """표가 없으면 만든다 (overseas 스키마는 이 앱 계정 소유라 직접 만들 수 있음)."""
    eng = engine()
    meta.create_all(eng)
    with eng.begin() as c:
        if c.execute(select(func.count()).select_from(channels)).scalar() == 0:
            c.execute(channels.insert(), [{"channel_id": i, "name": n, "active": True} for i, n in DEFAULT_CHANNELS])


def insert_new(table: Table, rows: list[dict], keys: list[str]) -> int:
    """이미 있는 행(keys 가 같은 것)은 건너뛰고 새 행만 넣는다. 넣은 개수를 돌려준다."""
    if not rows:
        return 0
    eng = engine()
    ins = pg_insert if eng.dialect.name == "postgresql" else sqlite_insert
    added = 0
    with eng.begin() as c:
        for i in range(0, len(rows), 300):
            stmt = ins(table).values(rows[i:i + 300]).on_conflict_do_nothing(index_elements=keys)
            added += c.execute(stmt).rowcount or 0
    return added


def read_df(stmt) -> pd.DataFrame:
    with engine().connect() as c:
        return pd.read_sql(stmt, c)


# ---- 관심종목 ----
def list_watchlist(active_only: bool = True) -> pd.DataFrame:
    stmt = select(watchlist).order_by(watchlist.c.added_at, watchlist.c.ticker)
    if active_only:
        stmt = stmt.where(watchlist.c.active.is_(True))
    return read_df(stmt)


def get_watch(ticker: str) -> dict | None:
    with engine().connect() as c:
        row = c.execute(select(watchlist).where(watchlist.c.ticker == ticker)).mappings().first()
    return dict(row) if row else None


def add_watch(ticker: str, name: str, cik: int | None, keywords: str, country: str = "US"):
    """새로 넣거나, 예전에 삭제한 종목이면 다시 살린다."""
    with engine().begin() as c:
        if c.execute(select(watchlist.c.ticker).where(watchlist.c.ticker == ticker)).first():
            c.execute(update(watchlist).where(watchlist.c.ticker == ticker).values(active=True))
        else:
            c.execute(watchlist.insert().values(ticker=ticker, country=country, name=name, cik=cik,
                                                keywords=keywords, active=True, added_at=now()))


def update_watch(ticker: str, **values):
    with engine().begin() as c:
        c.execute(update(watchlist).where(watchlist.c.ticker == ticker).values(**values))


# ---- 자료 ----
def known_uids(ticker: str, source: str) -> set[str]:
    with engine().connect() as c:
        rows = c.execute(select(items.c.uid).where(items.c.ticker == ticker, items.c.source == source))
        return {r[0] for r in rows}


def has_history(ticker: str) -> bool:
    with engine().connect() as c:
        return c.execute(select(fetch_log.c.id).where(fetch_log.c.ticker == ticker).limit(1)).first() is not None


def load_items(tickers: list[str], since: datetime, limit: int = 1500) -> pd.DataFrame:
    stmt = (select(items).where(items.c.ticker.in_(tickers), items.c.published_at >= since)
            .order_by(items.c.published_at.desc()).limit(limit))
    return read_df(stmt)


def last_runs() -> dict[str, datetime]:
    """종목별 마지막 업데이트 시각."""
    stmt = select(fetch_log.c.ticker, func.max(fetch_log.c.run_at)).group_by(fetch_log.c.ticker)
    with engine().connect() as c:
        return {t: pd.Timestamp(r).tz_convert("UTC") if pd.Timestamp(r).tzinfo else pd.Timestamp(r, tz="UTC")
                for t, r in c.execute(stmt) if t}


def load_log(limit: int = 2000) -> pd.DataFrame:
    return read_df(select(fetch_log).order_by(fetch_log.c.run_at.desc()).limit(limit))


# ---- 유튜브 채널 ----
def list_channels(active_only: bool = False) -> pd.DataFrame:
    stmt = select(channels).order_by(channels.c.name)
    if active_only:
        stmt = stmt.where(channels.c.active.is_(True))
    return read_df(stmt)


def save_channel(channel_id: str, name: str, active: bool = True):
    with engine().begin() as c:
        if c.execute(select(channels.c.channel_id).where(channels.c.channel_id == channel_id)).first():
            c.execute(update(channels).where(channels.c.channel_id == channel_id).values(name=name, active=active))
        else:
            c.execute(channels.insert().values(channel_id=channel_id, name=name, active=active))


def delete_channel(channel_id: str):
    with engine().begin() as c:
        c.execute(channels.delete().where(channels.c.channel_id == channel_id))
