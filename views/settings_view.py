"""설정: 유튜브 채널 관리. AI 모델 선택과 사용액은 3단계에서 추가."""
import re

import streamlit as st

from core import db
from sources import youtube


def render():
    st.header("설정")
    st.subheader("유튜브 채널")
    st.caption("체크한 채널의 새 영상 중 관심종목의 '영상 검색어'가 들어간 영상을 목록에 넣습니다. "
               "자막은 클라우드에서 막혀 제목과 설명만 받습니다.")
    ch = db.list_channels()
    edited = st.data_editor(ch, hide_index=True, width="stretch", key="ch_edit", disabled=["channel_id", "name"],
                            column_config={"channel_id": "채널 번호", "name": "채널", "active": "사용"})
    c1, c2 = st.columns([1, 3])
    if c1.button("변경 저장"):
        for r in edited.to_dict("records"):
            db.save_channel(r["channel_id"], r["name"], bool(r["active"]))
        st.toast("저장했습니다", icon="✅")

    with st.form("add_channel", clear_on_submit=True):
        cid = st.text_input("채널 추가", placeholder="채널 번호 (UC로 시작하는 24자리) 또는 youtube.com/channel/UC... 주소")
        if st.form_submit_button("추가"):
            m = re.search(r"UC[\w-]{22}", cid or "")
            if not m:
                st.error("채널 번호(UC...)를 찾지 못했습니다. 채널 페이지 → 정보 → 채널 공유 → '채널 ID 복사'로 얻을 수 있습니다.")
            else:
                try:
                    name = youtube.channel_feed_title(m.group(0))
                except Exception:
                    name = None
                if name:
                    db.save_channel(m.group(0), name)
                    st.rerun()
                st.error("그 번호의 채널을 찾지 못했습니다.")

    if not ch.empty:
        drop = st.selectbox("채널 삭제", [""] + ch["channel_id"].tolist(),
                            format_func=lambda c: dict(zip(ch["channel_id"], ch["name"])).get(c, "삭제할 채널 선택"))
        if st.button("삭제", disabled=not drop):
            db.delete_channel(drop)
            st.rerun()

    st.divider()
    st.subheader("AI 요약·번역")
    st.caption("3단계에서 모델 선택(기본 Claude Haiku 5.5)과 이번 달 사용액이 여기에 들어갑니다.")
