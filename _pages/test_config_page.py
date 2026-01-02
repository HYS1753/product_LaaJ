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
# Step Definitions
# =====================================================
STEPS = [
    {"id": 1, "key": "keywords", "label": "검색 키워드"},
    {"id": 2, "key": "api_a", "label": "시스템 A API"},
    {"id": 3, "key": "api_b", "label": "시스템 B API"},
    {"id": 4, "key": "review", "label": "검토"},
]


# =====================================================
# Page Entry
# =====================================================
def render():
    _init_state()

    # 상단 헤더: (좌) 타이틀/설명  (우) stepper
    head_l, head_r = st.columns([0.4, 0.6], vertical_alignment="bottom")
    with head_l:
        st.title("Test Settings")
        st.caption("검색 키워드 및 API 호출 조건을 단계별로 설정합니다.")
    with head_r:
        _render_stepper(current_step=st.session_state.current_step)

    # 타이틀/헤더와 본문 사이 여백
    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

    # Step Content
    step = st.session_state.current_step
    if step == 1:
        _render_step_keywords()
    elif step == 2:
        _render_step_api(system="A", step_key="2a")
    elif step == 3:
        _render_step_api(system="B", step_key="2b")
    elif step == 4:
        _render_step_review()

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
    _render_wizard_nav()



# =====================================================
# State / Validation
# =====================================================
def _init_state():
    if "current_step" not in st.session_state:
        st.session_state.current_step = 1

    # API 테스트 여부(Next gate 용)
    if "api_tested_A" not in st.session_state:
        st.session_state.api_tested_A = False
    if "api_tested_B" not in st.session_state:
        st.session_state.api_tested_B = False


def _can_go_next(step: int) -> bool:
    # 1) 키워드 step: 키워드 로드되어야 함
    if step == 1:
        return bool(get_keywords())

    # 2) 시스템 A step: URL 입력 + 테스트 성공(또는 완료 플래그)
    if step == 2:
        url = st.session_state.get("url_A", "")
        return bool(url.strip()) and bool(st.session_state.api_tested_A)

    # 3) 시스템 B step
    if step == 3:
        url = st.session_state.get("url_B", "")
        return bool(url.strip()) and bool(st.session_state.api_tested_B)

    # 4) review step은 next 없음
    return False


def _go_prev():
    st.session_state.current_step = max(1, st.session_state.current_step - 1)


def _go_next():
    st.session_state.current_step = min(len(STEPS), st.session_state.current_step + 1)


# =====================================================
# UI - Stepper / Nav
# =====================================================
def _render_stepper(current_step: int):
    items = []
    for s in STEPS:
        sid = s["id"]
        if sid < current_step:
            state = "done"
        elif sid == current_step:
            state = "active"
        else:
            state = "todo"
        items.append((sid, s["label"], state))

    html = ["<div class='stepper stepper-fit'>"]

    for i, (sid, label, state) in enumerate(items):
        html.append(f"""
          <div class='step {state}'>
            <div class='circle'>{sid}</div>
            <div class='label'>{label}</div>
          </div>
        """)
        if i != len(items) - 1:
            html.append("<div class='dash-line'></div>")

    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def _render_wizard_nav():
    step = st.session_state.current_step
    is_first = (step == 1)
    is_last = (step == len(STEPS))

    next_ok = _can_go_next(step)

    left, right = st.columns([1, 1])
    with left:
        st.button("← Prev", use_container_width=True, disabled=is_first, on_click=_go_prev)
    with right:
        if not is_last:
            st.button(
                "Next →",
                type="primary",
                use_container_width=True,
                disabled=not next_ok,
                on_click=_go_next
            )
        else:
            st.button("완료", type="primary", use_container_width=True, disabled=True)

    if not is_last and not next_ok:
        if step == 1:
            st.info("다음 단계로 이동하려면 검색 키워드를 로드해주세요.")
        elif step == 2:
            st.info("다음 단계로 이동하려면 시스템 A의 Endpoint 입력 후 테스트를 성공시켜주세요.")
        elif step == 3:
            st.info("다음 단계로 이동하려면 시스템 B의 Endpoint 입력 후 테스트를 성공시켜주세요.")


# =====================================================
# STEP 1. Keyword
# =====================================================
def _render_step_keywords():
    st.markdown("<div class='step-header'>", unsafe_allow_html=True)
    st.markdown("<div class='step-title'>1. 검색 키워드 설정</div>", unsafe_allow_html=True)
    st.markdown(
        """
        <div class='step-subtitle'>
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
    st.markdown("</div>", unsafe_allow_html=True)

    top1, top2, top3 = st.columns([2, 1, 1])
    with top1:
        method = st.selectbox(
            "입력 방식",
            ["텍스트 직접 입력", "텍스트 파일 업로드", "CSV 파일 업로드"],
            key="kw_method"
        )
    with top2:
        delimiter = st.text_input("구분자", value=",", help="예: , | ; 또는 \\n", key="kw_delim")
    with top3:
        if get_keywords():
            st.markdown("<span class='badge done'>로드 완료</span>", unsafe_allow_html=True)
        else:
            st.markdown("<span class='badge todo'>미로드</span>", unsafe_allow_html=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    text_input = None
    uploaded_file = None

    if method == "텍스트 직접 입력":
        text_input = st.text_area(
            "키워드 입력",
            placeholder="예: 파이썬 튜토리얼, 머신러닝 입문, 데이터 분석",
            height=140,
            key="kw_text"
        )
    elif method == "텍스트 파일 업로드":
        uploaded_file = st.file_uploader("텍스트 파일 선택 (.txt)", type=["txt"], key="kw_txt_file")
    else:
        uploaded_file = st.file_uploader("CSV 파일 선택 (.csv)", type=["csv"], key="kw_csv_file")
        st.caption("첫 번째 컬럼 데이터를 키워드로 사용합니다.")

    keywords = get_keywords()
    if keywords:
        with st.expander("로드된 키워드 미리보기 (상위 5개)", expanded=False):
            for i, kw in enumerate(get_keyword_preview(keywords, 5), 1):
                st.text(f"{i}. {kw}")
            if len(keywords) > 5:
                st.caption(f"... 외 {len(keywords) - 5}개")

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    if st.button("키워드 로드", type="primary", use_container_width=True):
        if method == "텍스트 직접 입력":
            if not text_input or not text_input.strip():
                st.warning("키워드를 입력해주세요.")
                return
            loaded = parse_keywords_from_text(text_input, delimiter)

        elif method == "텍스트 파일 업로드":
            if not uploaded_file:
                st.warning("먼저 텍스트 파일을 업로드해주세요.")
                return
            loaded = parse_keywords_from_file(uploaded_file, delimiter)

        else:
            if not uploaded_file:
                st.warning("먼저 CSV 파일을 업로드해주세요.")
                return
            loaded = parse_keywords_from_csv(uploaded_file)

        set_keywords(loaded)
        set_step_completed(1, True)
        st.success(f"{len(loaded)}개의 키워드가 정상적으로 로드되었습니다.")
        st.rerun()


# =====================================================
# STEP 2/3. API
# =====================================================
def _render_step_api(system: str, step_key: str):
    if not get_keywords():
        st.warning("먼저 검색 키워드를 설정해주세요.")
        return

    step_no = 2 if system == "A" else 3

    st.markdown("<div class='step-header'>", unsafe_allow_html=True)
    st.markdown(f"<div class='step-title'>{step_no}. 시스템 {system} API 설정</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='step-subtitle'>HTTP Method / Endpoint / 파라미터 / 응답 파싱 경로를 설정하고 단일 키워드로 테스트합니다.</div>",
        unsafe_allow_html=True
    )
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

    keywords = get_keywords()
    example_kw = keywords[0] if keywords else ""

    with st.container(border=True):
        c1, c2 = st.columns([1, 2])
        with c1:
            method = st.selectbox("HTTP Method", ["GET", "POST"], key=f"method_{system}")
        with c2:
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

        tested = st.session_state.get(f"api_tested_{system}", False)
        if tested:
            st.markdown("<span class='badge done'>테스트 성공</span>", unsafe_allow_html=True)
        else:
            st.markdown("<span class='badge todo'>미테스트</span>", unsafe_allow_html=True)

    with st.expander("고급 요청 설정", expanded=False):
        body = None
        if method == "POST":
            body = st.text_area("Request Body (JSON)", height=110, key=f"body_{system}")
        headers = st.text_area("HTTP Headers (JSON)", height=110, key=f"headers_{system}")

    with st.expander("응답 파싱", expanded=False):
        parse_path = st.text_input("JSON Path", placeholder="data.results.0.title", key=f"parse_{system}")

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    if st.button("API 테스트 실행", type="primary", use_container_width=True, key=f"test_{system}"):
        if not url or not url.strip():
            st.error("API Endpoint를 입력해주세요.")
            st.session_state[f"api_tested_{system}"] = False
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

        ok = _display_test_result(result, parse_path, step_key)
        st.session_state[f"api_tested_{system}"] = bool(ok)

        if ok:
            set_step_completed(step_key, True)

        st.rerun()


def _display_test_result(result, parse_path, step_key) -> bool:
    if not result["success"]:
        st.error(result["error"])
        return False

    st.success(f"호출 성공 (Status {result['status']})")

    with st.expander("전체 API 응답", expanded=False):
        st.json(result["data"])

    if parse_path:
        parsed = parse_json_path(result["data"], parse_path)
        if parsed is not None:
            st.markdown("**파싱 결과**")
            st.json(parsed)
        else:
            st.warning("파싱 결과가 없습니다.")

    return True


# =====================================================
# STEP 4. Review
# =====================================================
def _render_step_review():
    st.markdown("<div class='step-header'>", unsafe_allow_html=True)
    st.markdown("<div class='step-title'>4. 설정 검토</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='step-subtitle'>입력된 키워드 및 API 설정을 최종 확인합니다.</div>",
        unsafe_allow_html=True
    )
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

    kws = get_keywords() or []
    st.markdown("#### 키워드")
    if kws:
        st.markdown(f"- 총 **{len(kws)}개**")
        with st.expander("미리보기", expanded=False):
            for i, kw in enumerate(get_keyword_preview(kws, 10), 1):
                st.text(f"{i}. {kw}")
    else:
        st.warning("키워드가 없습니다.")

    st.markdown("#### API 설정")
    for system in ["A", "B"]:
        url = st.session_state.get(f"url_{system}", "")
        method = st.session_state.get(f"method_{system}", "")
        param = st.session_state.get(f"param_{system}", "")
        tested = st.session_state.get(f"api_tested_{system}", False)

        st.markdown(
            f"- **시스템 {system}**: `{method}` / `{url or '-'}` "
            f"(param: `{param or '-'}`) {'✅' if tested else '⚠️'}"
        )