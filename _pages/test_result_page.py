import streamlit as st
from utils.session_manager import get_keywords


def render():
    '''테스트 결과 페이지 렌더링'''
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.title("📊 테스트 결과")
    st.markdown("---")
    st.info("💡 테스트 실행 기능은 다음 단계에서 구현됩니다.")

    keywords = get_keywords()
    if keywords:
        st.metric("설정된 키워드 수", len(keywords))
    else:
        st.warning("아직 테스트를 실행하지 않았습니다. '테스트 설정 및 진행' 메뉴에서 테스트를 시작하세요.")

    st.markdown('</div>', unsafe_allow_html=True)