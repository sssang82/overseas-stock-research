"""자료 목록 (첫 화면): 업데이트 버튼, 거르기, 목록, 상세."""
from datetime import timedelta

import pandas as pd
import streamlit as st

from core import collect, config, db

KINDS = {"earnings": "실적", "filing": "공시", "insider": "내부자", "ownership": "지분", "grade": "등급",
         "news": "뉴스", "analysis": "분석", "video": "영상"}
PERIODS = {"최근 7일": 7, "최근 30일": 30, "최근 90일": 90, "최근 1년": 365}


def _update_box(wl: pd.DataFrame):
    c1, c2 = st.columns([4, 1])
    pick = c1.multiselect("업데이트할 종목", wl["ticker"].tolist(), placeholder="비워 두면 전체 종목")
    if c2.button("지금 업데이트", type="primary", width="stretch"):
        rows = wl[wl["ticker"].isin(pick)] if pick else wl
        bar = st.progress(0.0, "업데이트 준비 중...")
        logs = collect.update(rows.to_dict("records"),
                              lambda d, n, t: bar.progress(d / n, f"{t} 완료 ({d}/{n})"))
        bar.empty()
        added = sum(l["added"] or 0 for l in logs)
        failed = [f"{l['ticker'] or ''} {l['source']}".strip() for l in logs if l["status"] == "error"]
        st.session_state.update_msg = (f"새 자료 {added}건" +
                                       (f" · 실패 {len(failed)}곳: {', '.join(failed[:6])}" if failed else ""))
        st.rerun()
    if msg := st.session_state.get("update_msg"):
        st.success(msg + "  (실패 내용은 '수집 현황'에서 볼 수 있습니다)" if "실패" in msg else msg)


def _detail(r: dict):
    with st.container(border=True):
        st.subheader(r["표시 제목"])
        st.caption(f"{r['ticker']} · {KINDS.get(r['kind'], r['kind'])} · {r['publisher'] or ''} · "
                   f"{r['tier'] or ''} · {r['날짜']}")
        ex = r["extra"] or {}
        # SEC·등급은 제목을 직접 만들었으므로 원래 제목이 의미 없다
        if pd.notna(r["title_ko"]) and r["source"] not in ("sec", "yfinance"):
            st.write(f"원래 제목: {r['title']}")
        if f4 := ex.get("form4"):
            st.write(f"신고자: **{f4['owner'].title()}** {f4['role']}")
            if f4["transactions"]:
                st.dataframe(pd.DataFrame(f4["transactions"]).rename(columns={
                    "code": "코드", "action": "거래", "shares": "주식 수", "avg_price": "평균 단가($)"}),
                    hide_index=True)
        if ex.get("summary"):
            st.write(ex["summary"])
            st.caption("한국어 요약·번역은 다음 단계(3단계)에서 붙습니다.")
        c1, c2 = st.columns(2)
        if r["url"]:
            c1.link_button("원문 열기", r["url"], width="stretch")
        if ex.get("index_url"):
            c2.link_button("SEC 공시 첨부 목록", ex["index_url"], width="stretch")


def render():
    st.header("자료 목록")
    wl = db.list_watchlist()
    if wl.empty:
        st.info("먼저 '관심종목' 메뉴에서 종목을 추가하세요.")
        return
    _update_box(wl)

    f1, f2, f3, f4 = st.columns([2, 2, 1, 1])
    tickers = f1.multiselect("종목", wl["ticker"].tolist(), placeholder="전체 종목")
    kinds = f2.multiselect("종류", list(KINDS.values()), placeholder="전체 종류")
    period = f3.selectbox("기간", list(PERIODS), index=1)
    only_new = f4.checkbox("새 자료만", help="마지막 업데이트에서 새로 받은 자료")
    search = st.text_input("검색", placeholder="제목에서 찾을 말", label_visibility="collapsed")

    df = db.load_items(tickers or wl["ticker"].tolist(), db.now() - timedelta(days=PERIODS[period]))
    if df.empty:
        st.info("이 조건의 자료가 없습니다. 처음이라면 [지금 업데이트]를 눌러 주세요.")
        return
    for col in ("published_at", "fetched_at"):
        df[col] = pd.to_datetime(df[col], utc=True)
    last = db.last_runs()
    df["새로"] = [("●" if not ini and fa >= last.get(t, fa) else "")
                for t, fa, ini in zip(df["ticker"], df["fetched_at"], df["is_initial"].astype(bool))]
    df["종류"] = df["kind"].map(KINDS).fillna(df["kind"])
    df["표시 제목"] = df["title_ko"].fillna(df["title"])
    df["날짜"] = df["published_at"].dt.tz_convert(config.KST).dt.strftime("%m-%d %H:%M")
    if kinds:
        df = df[df["종류"].isin(kinds)]
    if only_new:
        df = df[df["새로"] == "●"]
    if search:
        df = df[df["표시 제목"].str.contains(search, case=False, regex=False)
                | df["title"].str.contains(search, case=False, regex=False)]
    df = df.reset_index(drop=True)
    st.caption(f"{len(df)}건 · 항목을 누르면 아래에 자세히 나옵니다")
    shown = df[["새로", "날짜", "ticker", "종류", "표시 제목", "publisher", "tier"]]
    sel = st.dataframe(shown, hide_index=True, width="stretch", height=480, on_select="rerun",
                       selection_mode="single-row", key="items_table",
                       column_config={"새로": st.column_config.TextColumn("", width=30), "ticker": "종목",
                                      "표시 제목": st.column_config.TextColumn("제목", width="large"),
                                      "publisher": "출처", "tier": "구분"})
    rows = sel.selection.rows if sel else []
    if rows and rows[0] < len(df):
        _detail(df.iloc[rows[0]].to_dict())
