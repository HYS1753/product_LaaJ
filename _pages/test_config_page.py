import streamlit as st
from utils.keyword_loader import (
    parse_keywords_from_text,
    parse_keywords_from_file,
    parse_keywords_from_csv,
    get_keyword_preview
)
from utils.api_handler import make_api_call, parse_json_path, parse_json_string
from utils.session_manager import (
    get_keywords, set_keywords,
    is_step_completed, set_step_completed
)

# =====================================================
# Page Entry
# =====================================================

def render():
    render_progress_sidebar()

    st.title("Test Settings")
    st.caption("검색 키워드 및 API 호출 조건을 단계별로 설정합니다.")
    st.markdown("---")

    render_keyword_section()
    st.markdown("---")
    render_api_section()


# =====================================================
# Sidebar Progress
# =====================================================

def render_progress_sidebar():
    with st.sidebar:
        st.markdown("### 진행 상태")

        steps = [
            ("1", "검색 키워드 설정"),
            ("2a", "시스템 A API"),
            ("2b", "시스템 B API"),
        ]

        for key, label in steps:
            done = is_step_completed(key)
            icon = "✓" if done else "•"
            st.markdown(f"{icon} {label}")


# =====================================================
# STEP 1. Keyword
# =====================================================
def render_keyword_section():
    left, right = st.columns([1, 2], gap="large")

    # ---------- LEFT : 설명 ----------
    with left:
        st.subheader("1. 검색 키워드 설정")
        st.markdown(
            """
            <div class="helper-text">
            테스트에 사용할 <b>검색 키워드 목록</b>을 설정합니다.<br><br>

            • 텍스트 직접 입력<br>
            • 텍스트 파일 업로드<br>
            • CSV 파일 업로드<br><br>

            입력된 키워드는 이후<br>
            <b>모든 API 테스트에 공통 적용</b>됩니다.
            </div>
            """,
            unsafe_allow_html=True
        )

    # ---------- RIGHT : 실제 작업 ----------
    with right:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)

        # 상단 컨트롤
        top_col1, top_col2, top_col3 = st.columns([2, 1, 1])

        with top_col1:
            method = st.selectbox(
                "입력 방식",
                ["텍스트 직접 입력", "텍스트 파일 업로드", "CSV 파일 업로드"]
            )

        with top_col2:
            delimiter = st.text_input(
                "구분자",
                value=",",
                help="예: , | ; 또는 \\n"
            )

        # 상태 표시
        with top_col3:
            if get_keywords():
                st.markdown(
                    '<div class="status-badge status-done">로드 완료</div>',
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    '<div class="status-badge status-pending">미로드</div>',
                    unsafe_allow_html=True
                )

        st.markdown("<hr style='margin:16px 0'>", unsafe_allow_html=True)

        # 입력 영역
        text_input = None
        uploaded_file = None

        if method == "텍스트 직접 입력":
            text_input = st.text_area(
                "키워드 입력",
                placeholder="예: 파이썬 튜토리얼, 머신러닝 입문, 데이터 분석",
                height=130
            )

        elif method == "텍스트 파일 업로드":
            uploaded_file = st.file_uploader(
                "텍스트 파일 선택 (.txt)",
                type=["txt"]
            )

        else:
            uploaded_file = st.file_uploader(
                "CSV 파일 선택 (.csv)",
                type=["csv"]
            )
            st.caption("첫 번째 컬럼 데이터를 키워드로 사용합니다.")

        # 🔍 키워드 미리보기
        keywords = get_keywords()
        if keywords:
            with st.expander("로드된 키워드 미리보기 (상위 5개)", expanded=False):
                for i, kw in enumerate(get_keyword_preview(keywords, 5), 1):
                    st.text(f"{i}. {kw}")
                if len(keywords) > 5:
                    st.caption(f"... 외 {len(keywords) - 5}개")

        st.markdown("")

        # 액션 버튼
        if st.button("키워드 로드", use_container_width=True):
            if method == "텍스트 직접 입력":
                if not text_input or not text_input.strip():
                    st.warning("키워드를 입력해주세요.")
                    return
                keywords = parse_keywords_from_text(text_input, delimiter)

            elif method == "텍스트 파일 업로드":
                if not uploaded_file:
                    st.warning("먼저 텍스트 파일을 업로드해주세요.")
                    return
                keywords = parse_keywords_from_file(uploaded_file, delimiter)

            else:
                if not uploaded_file:
                    st.warning("먼저 CSV 파일을 업로드해주세요.")
                    return
                keywords = parse_keywords_from_csv(uploaded_file)

            set_keywords(keywords)
            set_step_completed(1, True)

            st.success(f"{len(keywords)}개의 키워드가 정상적으로 로드되었습니다.")
            st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

def render_file_upload():
    col1, col2 = st.columns([1, 3])

    with col1:
        delimiter = st.selectbox("구분자", ["줄바꿈", "콤마"])

    with col2:
        file = st.file_uploader("TXT 파일", type=["txt"])

    if file and st.button("키워드 로드", type="primary", use_container_width=True):
        delimiter_value = "\n" if delimiter == "줄바꿈" else ","
        keywords = parse_keywords_from_file(file, delimiter_value)
        set_keywords(keywords)
        st.rerun()


def render_csv_upload():
    file = st.file_uploader("CSV 파일", type=["csv"])
    st.caption("첫 번째 컬럼을 키워드로 사용합니다.")

    if file and st.button("키워드 로드", type="primary", use_container_width=True):
        keywords = parse_keywords_from_csv(file)
        set_keywords(keywords)
        st.rerun()


# =====================================================
# STEP 2. API
# =====================================================

def render_api_section():
    st.subheader("2. 검색 API 설정")

    if not get_keywords():
        st.info("먼저 검색 키워드를 설정해주세요.")
        return

    tab_a, tab_b = st.tabs(["시스템 A", "시스템 B"])

    with tab_a:
        render_system_config("A", "2a")

    with tab_b:
        render_system_config("B", "2b")


def render_system_config(system: str, step_key: str):
    keywords = get_keywords()
    example_kw = keywords[0]

    left, right = st.columns([1, 2], gap="large")

    # ---------- LEFT : 설명 ----------
    with left:
        st.markdown(f"#### 시스템 {system}")
        st.markdown(
            """
            검색 API 호출 조건을 설정합니다.

            - HTTP Method
            - Endpoint
            - 파라미터
            - 응답 파싱 경로

            설정 후 **단일 키워드 테스트**를 수행할 수 있습니다.
            """
        )

    # ---------- RIGHT : 설정 ----------
    with right:
        with st.container(border=True):
            col1, col2 = st.columns([1, 2])

            with col1:
                method = st.selectbox(
                    "HTTP Method",
                    ["GET", "POST"],
                    key=f"method_{system}"
                )

            with col2:
                url = st.text_input(
                    "API Endpoint",
                    placeholder="https://api.example.com/search",
                    key=f"url_{system}"
                )

            keyword_param = st.text_input(
                "검색 키워드 파라미터명",
                value="query",
                key=f"param_{system}"
            )

        with st.expander("고급 요청 설정"):
            body = None
            if method == "POST":
                body = st.text_area(
                    "Request Body (JSON)",
                    height=100,
                    key=f"body_{system}"
                )

            headers = st.text_area(
                "HTTP Headers (JSON)",
                height=100,
                key=f"headers_{system}"
            )

        with st.expander("응답 파싱"):
            parse_path = st.text_input(
                "JSON Path",
                placeholder="data.results.0.title",
                key=f"parse_{system}"
            )

        if st.button("API 테스트 실행", type="primary", use_container_width=True, key=f"test_{system}"):
            if not url:
                st.error("API Endpoint를 입력해주세요.")
                return

            parsed_headers = parse_json_string(headers) if headers else None
            parsed_body = parse_json_string(body) if body else None

            with st.spinner("API 호출 중..."):
                result = make_api_call(
                    url,
                    method,
                    example_kw,
                    keyword_param,
                    parsed_headers,
                    parsed_body
                )

            display_test_result(result, parse_path, step_key)


# =====================================================
# Result
# =====================================================

def display_test_result(result, parse_path, step_key):
    if not result["success"]:
        st.error(result["error"])
        return

    set_step_completed(step_key, True)
    st.success(f"호출 성공 (Status {result['status']})")

    with st.expander("전체 API 응답"):
        st.json(result["data"])

    if parse_path:
        parsed = parse_json_path(result["data"], parse_path)
        if parsed is not None:
            st.markdown("**파싱 결과**")
            st.json(parsed)
        else:
            st.warning("파싱 결과가 없습니다.")