"""해외 관심종목 자료 앱."""
import hmac

import streamlit as st

from core import config, db

st.set_page_config(page_title="해외 관심종목", page_icon="🌏", layout="wide")


def check_password():
    """주소가 공개된 앱이라 비밀번호를 꼭 요구한다 (이 PC 시험 때만 생략)."""
    if config.is_local() or st.session_state.get("auth"):
        return
    pw = config.get("APP_PASSWORD")
    if not pw:
        st.error("앱 비밀번호(APP_PASSWORD)가 설정되지 않아 열 수 없습니다. Streamlit Secrets 에 넣어 주세요.")
        st.stop()
    entered = st.text_input("비밀번호", type="password")
    if entered and hmac.compare_digest(entered, pw):
        st.session_state.auth = True
        st.rerun()
    if entered:
        st.error("비밀번호가 맞지 않습니다")
    st.stop()


def check_db():
    if db.database_url() is None:
        st.error("데이터 저장소(OVERSEAS_DATABASE_URL)가 설정되지 않았습니다. Streamlit Secrets 에 넣어 주세요.")
        st.stop()
    if not st.session_state.get("db_ready"):
        try:
            db.init_db()
        except Exception as e:
            msg = str(e)
            url = db.database_url() or ""
            if "@" in url:  # 접속 주소의 비밀번호가 화면에 보이지 않게
                msg = msg.replace(url.split("@")[0].split(":")[-1], "***")
            st.error(f"데이터 저장소에 연결하지 못했습니다: {msg[:300]}")
            st.stop()
        st.session_state.db_ready = True


check_password()
check_db()

from views import items_view, settings_view, status_view, watchlist_view  # noqa: E402  (DB 확인 뒤에 불러온다)

PAGES = {"자료 목록": items_view.render, "관심종목": watchlist_view.render,
         "수집 현황": status_view.render, "설정": settings_view.render}
with st.sidebar:
    st.title("🌏 해외 관심종목")
    page = st.radio("메뉴", list(PAGES), label_visibility="collapsed")
PAGES[page]()
