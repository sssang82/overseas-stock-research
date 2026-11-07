"""설정값 읽기. 클라우드는 Streamlit Secrets(환경변수로도 들어옴), 이 PC는 .env 파일."""
import os
from datetime import timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))
MAX_WATCHLIST = 50
SEC_HISTORY_DAYS = 365


def _load_env(path: Path = ROOT / ".env"):
    """간단한 .env 로더. 이미 설정된 환경변수가 우선."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()


def get(key: str, default: str | None = None) -> str | None:
    if os.getenv(key):
        return os.environ[key]
    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception:  # Secrets 파일이 없는 경우
        return default


def is_local() -> bool:
    """이 PC에서 시험할 때만 SQLite 를 허용한다 (클라우드에서 데이터가 사라지는 일 방지)."""
    return get("LOCAL_DEV") == "1"
