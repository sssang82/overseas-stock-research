"""해외 관심종목 앱 — 1단계: 클라우드 서버에서 자료원 접속 시험."""
import pandas as pd
import streamlit as st

from probes import run_all

st.set_page_config(page_title="해외주식 접속 시험", layout="wide")
st.title("자료원 접속 시험")
st.caption("이 서버에서 각 자료가 받아지는지 확인합니다. 저장하는 정보는 없습니다.")

if st.button("시험 시작", type="primary"):
    rows, table = [], st.empty()
    with st.spinner("시험 중... (1분 안팎)"):
        for row in run_all():
            rows.append(row)
            table.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    ok = sum(r["결과"] == "✅" for r in rows)
    st.success(f"완료: {len(rows)}개 중 {ok}개 성공")
