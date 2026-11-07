"""수집 현황: 종목·자료원별 마지막 결과와 실패 내용, 접속 시험."""
import pandas as pd
import streamlit as st

from core import config, db

SOURCES = {"sec": "SEC 공시", "yahoo": "Yahoo", "google": "Google News", "nasdaq": "Nasdaq",
           "seekingalpha": "Seeking Alpha", "yfinance": "애널리스트 등급", "youtube": "유튜브"}


def render():
    st.header("수집 현황")
    log = db.load_log()
    if log.empty:
        st.info("아직 업데이트 기록이 없습니다.")
    else:
        log["run_at"] = pd.to_datetime(log["run_at"], utc=True).dt.tz_convert(config.KST)
        latest = log.sort_values("run_at").groupby(["ticker", "source"], dropna=False).tail(1)
        latest = latest.assign(자료원=latest["source"].map(lambda s: SOURCES.get(s, s)),
                               결과=latest["status"].map({"ok": "✅", "error": "❌"}),
                               시각=latest["run_at"].dt.strftime("%m-%d %H:%M"))
        st.subheader("마지막 업데이트 결과")
        st.dataframe(latest[["ticker", "자료원", "결과", "found", "added", "seconds", "시각", "message"]]
                     .sort_values(["ticker", "자료원"], na_position="first"), hide_index=True, width="stretch",
                     column_config={"ticker": "종목", "found": "받은 건수", "added": "새로 저장",
                                    "seconds": "초", "message": "실패 내용"})
        runs = log.groupby("run_at").agg(종목=("ticker", "nunique"), 새자료=("added", "sum"),
                                         실패=("status", lambda s: (s == "error").sum()))
        st.subheader("최근 업데이트")
        st.dataframe(runs.sort_index(ascending=False).head(20).reset_index()
                     .assign(run_at=lambda d: d["run_at"].dt.strftime("%m-%d %H:%M"))
                     .rename(columns={"run_at": "시각"}), hide_index=True)

    with st.expander("자료원 접속 시험 (1단계 시험과 같음)"):
        if st.button("시험 시작"):
            from probes import run_all
            rows, table = [], st.empty()
            for row in run_all():
                rows.append(row)
                table.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
