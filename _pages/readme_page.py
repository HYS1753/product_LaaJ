import streamlit as st


def render():
    '''README 페이지 렌더링'''
    st.title("LLM as a Judge")
    st.markdown("---")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown('''
        ### 🎯 개요
        **LLM as a Judge**는 대규모 언어 모델을 활용하여 두 개의 검색 시스템을 객관적으로 비교·평가하는 자동화 도구입니다.

        ### ✨ 주요 기능
        - **자동화된 평가**: 여러 검색 키워드에 대해 일괄 테스트
        - **공정한 비교**: 동일한 조건에서 A/B 시스템 비교
        - **유연한 설정**: GET/POST 요청, 다양한 API 형식 지원
        - **상세한 분석**: LLM 기반의 정성적 평가

        ### 📋 사용 방법
        1. **검색 키워드 설정**: 텍스트 파일, CSV 또는 직접 입력
        2. **API 설정**: 테스트할 두 시스템의 API 정보 입력
        3. **테스트 실행**: 자동으로 모든 키워드 테스트
        4. **결과 분석**: LLM이 평가한 결과 확인
        ''')

    with col2:
        st.info('''
        **💡 Tip**

        검색 키워드는 실제 사용자가 
        검색할 만한 다양한 쿼리를 
        포함하는 것이 좋습니다.

        API 응답 형식이 JSON이어야 
        정확한 파싱이 가능합니다.
        ''')

    st.markdown('</div>', unsafe_allow_html=True)

    st.success("👈 왼쪽 사이드바에서 **Test Settings**을 선택하여 시작하세요!")