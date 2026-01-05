import json
from datetime import datetime
import streamlit as st

from utils.keyword_loader import (
    parse_keywords_from_text,
    parse_keywords_from_file,
    parse_keywords_from_csv,
    get_keyword_preview
)
from utils.api_handler import (
    make_api_call,
    parse_json_path,
    parse_json_string,
    merge_query_params,
    build_curl
)
from utils.session_manager import (
    get_keywords,
    set_keywords,
    set_step_completed
)

# =====================================================
# Step Definitions
# =====================================================
STEPS = [
    {"id": 1, "key": "keywords", "label": "Search Keywords"},
    {"id": 2, "key": "control_group", "label": "Control Group"},
    {"id": 3, "key": "experimental_group", "label": "Experimental Group"},
    {"id": 4, "key": "review", "label": "Review"},
    {"id": 5, "key": "test_data_generation", "label": "Test Data Generation"},
]

GROUPS = [
    {"name": "Control", "prefix": "control"},
    {"name": "Experimental", "prefix": "experimental"},
]

# =====================================================
# Page Entry
# =====================================================
def render():
    _init_state()

    st.title("A/B Test Settings")
    st.caption("검색 키워드 및 대조군(Control Group) / 실험군(Experimental Group) 조건을 단계별로 설정합니다.")
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    _render_stepper(current_step=st.session_state.current_step)
    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    st.markdown("<div style='height:50px'></div>", unsafe_allow_html=True)

    step = st.session_state.current_step
    if step == 1:
        _render_step_keywords()
    elif step == 2:
        _render_step_api(group_name="Control", group_prefix="control", step_key="2a", step_no=2)
    elif step == 3:
        _render_step_api(group_name="Experimental", group_prefix="experimental", step_key="2b", step_no=3)
    elif step == 4:
        _render_step_review()
    elif step == 5:
        _render_step_generation()

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
    _render_wizard_nav()

    if st.session_state.get("nav_alert"):
        st.toast(st.session_state.pop("nav_alert"), icon="⚠️")


# =====================================================
# State / Validation
# =====================================================
def _init_state():
    if "current_step" not in st.session_state:
        st.session_state.current_step = 1

    # ✅ step completion flags (Next gate)
    if "step_2a_completed" not in st.session_state:
        st.session_state.step_2a_completed = False
    if "step_2b_completed" not in st.session_state:
        st.session_state.step_2b_completed = False

    # ✅ tested flags (optional UI)
    if "control_tested" not in st.session_state:
        st.session_state.control_tested = False
    if "experimental_tested" not in st.session_state:
        st.session_state.experimental_tested = False

    # ✅ generation results persistence
    if "generated_payload" not in st.session_state:
        st.session_state.generated_payload = None


def _can_go_next(step: int) -> bool:
    if step == 1:
        return bool(get_keywords())

    if step == 2:
        return bool(st.session_state.step_2a_completed)

    if step == 3:
        return bool(st.session_state.step_2b_completed)

    if step == 4:
        # review는 generation으로 넘어가게 허용(키워드+양쪽 step 완료 조건)
        return bool(get_keywords()) and st.session_state.step_2a_completed and st.session_state.step_2b_completed

    # step 5는 next 없음
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


def _on_next_clicked():
    step = st.session_state.current_step

    if _can_go_next(step):
        _go_next()
        return

    if step == 1:
        msg = "다음 단계로 이동하려면 검색 키워드를 로드해주세요."
    elif step == 2:
        msg = "다음 단계로 이동하려면 Control Group 설정 후 테스트를 성공시켜주세요."
    elif step == 3:
        msg = "다음 단계로 이동하려면 Experimental Group 설정 후 테스트를 성공시켜주세요."
    elif step == 4:
        msg = "Test Data Generation으로 이동하려면 키워드/Control/Experimental 설정이 모두 완료되어야 합니다."
    else:
        msg = "다음 단계로 이동할 수 없습니다."

    st.session_state.nav_alert = msg


def _render_wizard_nav():
    step = st.session_state.current_step
    is_first = (step == 1)
    is_last = (step == len(STEPS))

    # ✅ Next가 맨 오른쪽, Back이 그 왼쪽
    spacer, c_back, c_next = st.columns([0.78, 0.10, 0.12], gap="small", vertical_alignment="center")

    with c_back:
        st.button("‹ Back", use_container_width=True, disabled=is_first, on_click=_go_prev)

    with c_next:
        if not is_last:
            st.button("Next ›", type="primary", use_container_width=True, on_click=_on_next_clicked)
        else:
            st.button("완료", type="primary", use_container_width=True, disabled=True)


# =====================================================
# STEP 1. Keyword
# =====================================================
def _render_step_keywords():
    left, right = st.columns([0.42, 0.58], gap="large", vertical_alignment="top")

    with left:
        st.markdown("<div class='step-title'>1. Search Keywords Setting</div>", unsafe_allow_html=True)
        st.markdown(
            """
            <div class='sub'>
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

    with right:
        top1, top2 = st.columns([2, 1], vertical_alignment="center")
        with top1:
            method = st.selectbox(
                "입력 방식",
                ["텍스트 직접 입력", "텍스트 파일 업로드", "CSV 파일 업로드"],
                key="kw_method"
            )
        delimiter = st.session_state.get("kw_delim", ",")
        if method != "CSV 파일 업로드":
            with top2:
                delimiter = st.text_input("구분자", value=delimiter, help="예: , | ; 또는 \\n", key="kw_delim")

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
            uploaded_file = st.file_uploader(
                "CSV 파일 선택 (.csv) - 첫 번째 컬럼 데이터를 키워드로 사용합니다.",
                type=["csv"],
                key="kw_csv_file"
            )

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
# Helpers - Config I/O
# =====================================================
def _cfg(prefix: str) -> dict:
    """Read current group config from session_state using a stable prefix."""
    fixed_key = f"{prefix}_fixed_params"
    fixed_rows = st.session_state.get(fixed_key, [])
    fixed_params = {r.get("k"): r.get("v") for r in fixed_rows if (r.get("k") or "").strip()}

    headers_text = st.session_state.get(f"{prefix}_headers", "")
    body_text = st.session_state.get(f"{prefix}_body", "")

    return {
        "method": st.session_state.get(f"{prefix}_method", "GET"),
        "url": st.session_state.get(f"{prefix}_url", ""),
        "keyword_param": st.session_state.get(f"{prefix}_param", "query"),
        "fixed_params": fixed_params,
        "headers": parse_json_string(headers_text) if headers_text else None,
        "base_body": parse_json_string(body_text) if body_text else None,
        "parse_path": st.session_state.get(f"{prefix}_parse", ""),
        "tested": bool(st.session_state.get(f"{prefix}_tested", False)),
        "last_curl": st.session_state.get(f"{prefix}_last_curl", ""),
    }


def _ensure_fixed_rows(prefix: str):
    fixed_key = f"{prefix}_fixed_params"
    if fixed_key not in st.session_state:
        st.session_state[fixed_key] = []


def _build_request_for_keyword(prefix: str, keyword: str):
    """Return (call_url, method, keyword_param, headers, body, curl_display)"""
    cfg = _cfg(prefix)
    method = cfg["method"]
    url = (cfg["url"] or "").strip()
    keyword_param = cfg["keyword_param"]
    headers = cfg["headers"]

    fixed_params = cfg["fixed_params"] or {}
    base_body = cfg["base_body"] if isinstance(cfg["base_body"], dict) else {}

    if method == "GET":
        # 고정 파라미터는 URL query로
        call_url = merge_query_params(url, fixed_params)
        curl_url = merge_query_params(call_url, {keyword_param: keyword})
        body = None
        curl = build_curl("GET", curl_url, headers, None)
        return call_url, "GET", keyword_param, headers, body, curl

    # POST: 고정 파라미터는 body(query_body)로 + keyword_param은 make_api_call이 넣는 방식 유지
    # (base_body + fixed_params만 넘기고 keyword는 make_api_call의 keyword/keyword_param 인자로 주입)
    body = dict(base_body)
    body.update(fixed_params)
    curl_body = dict(body)
    curl_body[keyword_param] = keyword
    curl = build_curl("POST", url, headers, curl_body)
    return url, "POST", keyword_param, headers, body, curl


# =====================================================
# STEP 2/3. API
# =====================================================
def _render_step_api(group_name: str, group_prefix: str, step_key: str, step_no: int):
    if not get_keywords():
        st.warning("먼저 검색 키워드를 설정해주세요.")
        return

    _ensure_fixed_rows(group_prefix)
    keywords = get_keywords()
    example_kw = keywords[0] if keywords else ""

    # persistence keys
    last_result_key = f"{group_prefix}_last_result"
    last_curl_key = f"{group_prefix}_last_curl"
    last_error_key = f"{group_prefix}_last_error"

    left, right = st.columns([0.42, 0.58], gap="large", vertical_alignment="top")

    with left:
        st.markdown(f"<div class='step-title'>{step_no}. {group_name} Group Setting</div>", unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="sub" style="line-height:1.7">
            이 단계에서는 <b>검색 키워드</b>를 이용해 실제 API 호출이 어떻게 이루어지는지 테스트합니다.
            <br><br>

            <b>키워드 파라미터</b><br>
            • 아래에서 지정한 파라미터명에<br>
            • 1단계에서 설정한 <b>검색 키워드 목록이 순차적으로</b> 들어가 호출됩니다.
            <br><br>

            <b>요청 방식</b><br>
            • <b>GET</b>: 키워드 + 고정 파라미터 → URL QueryString<br>
            • <b>POST</b>: 키워드 + 고정 파라미터 → JSON Body (query_body)
            <br><br>

            <b>응답 파싱</b><br>
            • 비워두면 전체 응답을 사용합니다.<br>
            • <code>data.items.0.title</code> 처럼 <code>.</code>으로 경로를 지정하면 해당 값만 추출합니다.
            </div>
            """,
            unsafe_allow_html=True
        )

    with right:
        st.markdown("**Default Settings**")

        c1, c2 = st.columns([1, 2])
        with c1:
            st.selectbox("HTTP Method", ["GET", "POST"], key=f"{group_prefix}_method")
        with c2:
            st.text_input(
                "API Endpoint",
                placeholder="https://api.example.com/search",
                key=f"{group_prefix}_url"
            )

        st.text_input(
            "검색 키워드 파라미터명 (1단계 설정 키워드 순차 호출 대상 필드)",
            value=st.session_state.get(f"{group_prefix}_param", "query"),
            help=f"예: query / q / keyword (테스트 예시: {example_kw})",
            key=f"{group_prefix}_param"
        )

        st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

        st.markdown("**Extra Parameters Settings**")
        with st.expander("고정 파라미터", expanded=False):
            st.markdown(
                "<div class='sub' style='margin-top:-4px'>"
                "이 API 호출에 항상 포함되는 파라미터입니다. "
                "GET은 QueryString, POST는 JSON Body(query_body)로 전달됩니다."
                "</div>",
                unsafe_allow_html=True
            )

            h1, h2, h3 = st.columns([0.44, 0.44, 0.12])
            with h1:
                st.caption("Key")
            with h2:
                st.caption("Value")
            with h3:
                st.caption("")

            fixed_rows_key = f"{group_prefix}_fixed_params"
            for i, row in enumerate(st.session_state[fixed_rows_key]):
                with st.container(border=True):
                    cc1, cc2, cc3 = st.columns([0.40, 0.40, 0.20], vertical_alignment="center")

                    with cc1:
                        row["k"] = st.text_input(
                            "Key",
                            value=row.get("k", ""),
                            placeholder="예: lang",
                            label_visibility="collapsed",
                            key=f"{fixed_rows_key}_k_{i}"
                        )
                    with cc2:
                        row["v"] = st.text_input(
                            "Value",
                            value=row.get("v", ""),
                            placeholder="예: ko",
                            label_visibility="collapsed",
                            key=f"{fixed_rows_key}_v_{i}"
                        )
                    with cc3:
                        if st.button("삭제", key=f"{fixed_rows_key}_del_{i}"):
                            st.session_state[fixed_rows_key].pop(i)
                            st.rerun()

            if st.button("＋ 파라미터 추가", use_container_width=True, key=f"{fixed_rows_key}_add"):
                st.session_state[fixed_rows_key].append({"k": "", "v": ""})
                st.rerun()

        with st.expander("고급 요청 설정", expanded=False):
            st.text_area("HTTP Headers (JSON)", height=90, key=f"{group_prefix}_headers")
            if st.session_state.get(f"{group_prefix}_method", "GET") == "POST":
                st.text_area("기본 Request Body (JSON)", height=110, key=f"{group_prefix}_body")

        st.text_input(
            "응답 파싱 경로 (선택)",
            placeholder="예: data.items.0.title",
            key=f"{group_prefix}_parse"
        )

        # status badge (항상 현재 상태 기반)
        tested = bool(st.session_state.get(f"{group_prefix}_tested", False))
        st.markdown(
            "<span class='badge done'>테스트 성공</span>" if tested else "<span class='badge todo'>미테스트</span>",
            unsafe_allow_html=True
        )

        if st.button("API 테스트 실행", type="primary", use_container_width=True, key=f"{group_prefix}_test"):
            st.session_state[last_error_key] = None

            cfg = _cfg(group_prefix)
            url = (cfg["url"] or "").strip()
            if not url:
                st.session_state[last_error_key] = "API Endpoint를 입력해주세요."
                st.session_state[f"{group_prefix}_tested"] = False
                st.rerun()

            try:
                call_url, method, keyword_param, headers, body, curl = _build_request_for_keyword(group_prefix, example_kw)

                result = make_api_call(
                    call_url,
                    method,
                    example_kw,
                    keyword_param,
                    headers,
                    body
                )

                st.session_state[last_result_key] = result
                st.session_state[last_curl_key] = curl
                st.session_state[f"{group_prefix}_last_curl"] = curl

                ok = bool(result.get("success", False))
                st.session_state[f"{group_prefix}_tested"] = ok

                if ok:
                    # step completed flags for Next gate
                    if step_key == "2a":
                        st.session_state.step_2a_completed = True
                    elif step_key == "2b":
                        st.session_state.step_2b_completed = True

                    set_step_completed(step_key, True)
                else:
                    st.session_state[last_error_key] = result.get("error", "호출 실패")

            except Exception as e:
                st.session_state[last_error_key] = str(e)
                st.session_state[f"{group_prefix}_tested"] = False

            st.rerun()

        # ----- Result display (persisted) -----
        if st.session_state.get(last_curl_key):
            with st.expander("curl 호출 방식", expanded=True):
                st.code(st.session_state[last_curl_key], language="bash")

        if st.session_state.get(last_error_key):
            with st.expander("오류 상세", expanded=True):
                st.error(st.session_state[last_error_key])

        if st.session_state.get(last_result_key):
            res = st.session_state[last_result_key]
            if res.get("success"):
                st.success(f"호출 성공 (Status {res.get('status')})")
                with st.expander("API 응답", expanded=False):
                    st.json(res.get("data"))

                parse_path = st.session_state.get(f"{group_prefix}_parse", "")
                if parse_path:
                    parsed = parse_json_path(res.get("data"), parse_path)
                    if parsed is not None:
                        st.markdown("**파싱 결과**")
                        st.json(parsed)
                    else:
                        with st.expander("파싱 오류", expanded=True):
                            st.warning("지정한 경로에서 값을 찾을 수 없습니다.")


# =====================================================
# STEP 4. Review (상용서비스급 정리)
# =====================================================
def _render_step_review():
    left, right = st.columns([0.42, 0.58], gap="large", vertical_alignment="top")

    with left:
        st.markdown("<div class='step-title'>4. Review</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='sub'>현재 설정된 키워드/그룹 설정을 최종 확인합니다.</div>",
            unsafe_allow_html=True
        )

    with right:
        # Keywords summary
        kws = get_keywords() or []
        st.markdown("### Search Keywords")
        if kws:
            st.markdown(f"- 총 **{len(kws)}개**")
            with st.expander("미리보기 (상위 10개)", expanded=False):
                for i, kw in enumerate(get_keyword_preview(kws, 10), 1):
                    st.text(f"{i}. {kw}")
        else:
            st.warning("키워드가 없습니다.")

        st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

        # Group configs
        for g in GROUPS:
            name = g["name"]
            prefix = g["prefix"]
            cfg = _cfg(prefix)

            st.markdown(f"### {name} Group")
            st.markdown(
                f"- Method: `{cfg['method']}`\n"
                f"- Endpoint: `{cfg['url'] or '-'}`\n"
                f"- Keyword Param: `{cfg['keyword_param'] or '-'}`\n"
                f"- Parse Path: `{cfg['parse_path'] or '-'}`\n"
                f"- Tested: {'✅' if cfg['tested'] else '⚠️'}"
            )

            fixed_params = cfg["fixed_params"] or {}
            headers = cfg["headers"] or {}
            base_body = cfg["base_body"] if isinstance(cfg["base_body"], dict) else {}

            with st.expander(f"{name} 세부 설정 보기", expanded=False):
                st.markdown("**Extra Parameters**")
                if fixed_params:
                    st.json(fixed_params)
                else:
                    st.caption("설정된 고정 파라미터가 없습니다.")

                st.markdown("**Headers**")
                st.json(headers)

                if cfg["method"] == "POST":
                    st.markdown("**Base Body (키워드/고정 파라미터 합쳐지기 전 기본 바디)**")
                    st.json(base_body)

                if cfg["last_curl"]:
                    st.markdown("**Last curl preview**")
                    st.code(cfg["last_curl"], language="bash")

        st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
        st.info("Review를 확인한 후 Next를 눌러 Test Data Generation 단계로 이동하세요.")


# =====================================================
# STEP 5. Test Data Generation
# =====================================================
def _render_step_generation():
    left, right = st.columns([0.42, 0.58], gap="large", vertical_alignment="top")

    with left:
        st.markdown("<div class='step-title'>5. Test Data Generation</div>", unsafe_allow_html=True)
        st.markdown(
            """
            <div class='sub' style="line-height:1.7">
            Control / Experimental 설정값으로<br>
            1단계에서 설정한 <b>전체 키워드</b>를 순차 호출하여 테스트 데이터를 생성합니다.<br><br>
            • 각 키워드마다 Control/Experimental 모두 호출<br>
            • 파싱 경로가 있으면 파싱 결과 저장, 없으면 전체 응답 저장<br>
            • 설정 + 결과를 JSON으로 묶어 다운로드합니다.
            </div>
            """,
            unsafe_allow_html=True
        )

    with right:
        kws = get_keywords() or []
        if not kws:
            st.warning("키워드가 없습니다. 1단계에서 키워드를 먼저 로드해주세요.")
            return

        # gate check
        if not (st.session_state.step_2a_completed and st.session_state.step_2b_completed):
            st.warning("Control/Experimental 설정을 완료(테스트 성공)한 뒤에 생성할 수 있습니다.")
            return

        st.markdown("### Generate")
        st.caption(f"총 {len(kws)}개 키워드를 Control/Experimental로 모두 호출합니다.")

        run = st.button("테스트 데이터 생성", type="primary", use_container_width=True)
        if run:
            progress = st.progress(0)
            status = st.empty()

            results = []
            total = len(kws)

            # configs snapshot
            control_cfg = _cfg("control")
            exp_cfg = _cfg("experimental")

            for idx, kw in enumerate(kws, start=1):
                status.write(f"Generating... ({idx}/{total}) — `{kw}`")

                row = {"keyword": kw, "control": {}, "experimental": {}}

                # Control
                c_url, c_method, c_kp, c_headers, c_body, c_curl = _build_request_for_keyword("control", kw)
                c_res = make_api_call(c_url, c_method, kw, c_kp, c_headers, c_body)

                row["control"]["curl"] = c_curl
                row["control"]["success"] = bool(c_res.get("success"))
                row["control"]["status"] = c_res.get("status")
                row["control"]["error"] = c_res.get("error")
                row["control"]["raw"] = c_res.get("data") if c_res.get("success") else None
                c_parse = control_cfg.get("parse_path") or ""
                if c_res.get("success"):
                    if c_parse:
                        try:
                            row["control"]["parsed"] = parse_json_path(c_res.get("data"), c_parse)
                        except Exception as e:
                            row["control"]["parsed_error"] = str(e)
                    else:
                        row["control"]["parsed"] = c_res.get("data")

                # Experimental
                e_url, e_method, e_kp, e_headers, e_body, e_curl = _build_request_for_keyword("experimental", kw)
                e_res = make_api_call(e_url, e_method, kw, e_kp, e_headers, e_body)

                row["experimental"]["curl"] = e_curl
                row["experimental"]["success"] = bool(e_res.get("success"))
                row["experimental"]["status"] = e_res.get("status")
                row["experimental"]["error"] = e_res.get("error")
                row["experimental"]["raw"] = e_res.get("data") if e_res.get("success") else None
                e_parse = exp_cfg.get("parse_path") or ""
                if e_res.get("success"):
                    if e_parse:
                        try:
                            row["experimental"]["parsed"] = parse_json_path(e_res.get("data"), e_parse)
                        except Exception as e:
                            row["experimental"]["parsed_error"] = str(e)
                    else:
                        row["experimental"]["parsed"] = e_res.get("data")

                results.append(row)
                progress.progress(idx / total)

            status.success("완료! 테스트 데이터가 생성되었습니다.")

            payload = {
                "meta": {
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                    "keyword_count": len(kws),
                },
                "keywords": kws,
                "control_config": control_cfg,
                "experimental_config": exp_cfg,
                "results": results,
            }

            st.session_state.generated_payload = payload

        # show/download if exists
        if st.session_state.get("generated_payload"):
            st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
            st.markdown("### Output")
            with st.expander("생성된 JSON 미리보기", expanded=False):
                st.json(st.session_state.generated_payload)

            json_bytes = json.dumps(st.session_state.generated_payload, ensure_ascii=False, indent=2).encode("utf-8")
            st.download_button(
                label="JSON 다운로드",
                data=json_bytes,
                file_name=f"ab_test_data_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                use_container_width=True,
            )
