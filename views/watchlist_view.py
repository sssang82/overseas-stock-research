"""관심종목 등록·수정·삭제."""
import re

import streamlit as st

from core import config, db
from sources import sec

TEST_TICKERS = ["NVDA", "MRNA", "GOOGL", "TSLA", "MU"]
ALIASES = {"GOOGL": "Google", "GOOG": "Google"}  # 회사명만으로는 영상 검색이 부족한 종목
SUFFIX = re.compile(r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|holdings?|group|"
                    r"class [a-c]|the)\b\.?", re.I)


def default_keywords(ticker: str, name: str) -> str:
    """'MICRON TECHNOLOGY INC' → 'Micron'. 유튜브 영상을 찾을 때 쓰는 이름."""
    base = re.sub(r"[,.]", " ", SUFFIX.sub(" ", name)).split()
    words = [base[0].title() if base and len(base[0]) >= 4 else " ".join(base).title()]
    if ticker in ALIASES:
        words.append(ALIASES[ticker])
    return ", ".join(w for w in words if w)


def add(ticker: str) -> str | None:
    """종목을 추가하고, 실패하면 이유를 돌려준다."""
    ticker = ticker.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", ticker):
        return f"'{ticker}' 는 티커 형식이 아닙니다"
    if len(db.list_watchlist()) >= config.MAX_WATCHLIST:
        return f"관심종목은 {config.MAX_WATCHLIST}개까지 등록할 수 있습니다"
    found = sec.lookup(ticker)
    if not found:
        return f"{ticker}: SEC 에 등록된 미국 상장 종목이 아닙니다"
    cik, name = found
    old = db.get_watch(ticker)
    db.add_watch(ticker, name.title(), cik, old["keywords"] if old else default_keywords(ticker, name))
    return None


def render():
    st.header("관심종목")
    wl = db.list_watchlist()
    st.caption(f"{len(wl)} / {config.MAX_WATCHLIST}개 · 미국 종목만 (일본·중국은 이후 추가)")

    with st.form("add", clear_on_submit=True):
        c1, c2 = st.columns([3, 1])
        ticker = c1.text_input("티커로 추가", placeholder="예: AAPL, 여러 개는 쉼표로 구분")
        if c2.form_submit_button("추가", width="stretch") and ticker:
            for t in [t for t in re.split(r"[,\s]+", ticker) if t]:
                err = add(t)
                st.toast(err or f"{t.upper()} 추가", icon="⚠️" if err else "✅")
            st.rerun()

    if wl.empty:
        st.info("등록된 종목이 없습니다.")
        if st.button(f"시험 종목 5개 추가 ({', '.join(TEST_TICKERS)})", type="primary"):
            for t in TEST_TICKERS:
                if err := add(t):
                    st.error(err)
            st.rerun()
        return

    st.write("**영상 검색어**는 유튜브 영상 제목·설명에서 찾을 이름입니다 (쉼표로 구분). **메모**에는 편입 이유 등을 적어 두세요.")
    edited = st.data_editor(
        wl[["ticker", "name", "keywords", "memo"]], hide_index=True, width="stretch", key="wl_edit",
        disabled=["ticker", "name"],
        column_config={"ticker": "티커", "name": "회사명", "keywords": "영상 검색어", "memo": "메모"})
    c1, c2, c3 = st.columns([1, 2, 1])
    if c1.button("변경 저장"):
        for old, new in zip(wl.to_dict("records"), edited.to_dict("records")):
            if (old["keywords"], old["memo"]) != (new["keywords"], new["memo"]):
                db.update_watch(new["ticker"], keywords=new["keywords"], memo=new["memo"])
        st.toast("저장했습니다", icon="✅")
    remove = c2.selectbox("삭제할 종목", [""] + wl["ticker"].tolist(), label_visibility="collapsed",
                          format_func=lambda t: t or "삭제할 종목 선택")
    if c3.button("삭제", disabled=not remove):
        db.update_watch(remove, active=False)
        st.toast(f"{remove} 삭제 (받아 둔 자료는 남아 있어 다시 추가하면 보입니다)")
        st.rerun()
