import json
from datetime import datetime
from pathlib import Path
from typing import List
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
    {"id": 0, "key": "intro", "label": "Overview"},
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
# ✅ FIX: Single Source of Truth (setting snapshot)
# =====================================================
def _default_group_cfg():
    return {
        "method": "GET",
        "url": "",
        "param": "query",
        "headers": "",
        "body": "",
        "parse": "",
        "fixed_params_rows": [],  # [{"k": "...", "v": "..."}]
        "tested": False,
        "last_curl": "",
        "last_result": None,
        "last_error": None,
    }


def _init_setting_store():
    if "ab_setting" not in st.session_state:
        st.session_state.ab_setting = {
            "test_name": "",
            "keywords": {
                "kw_method": "텍스트 직접 입력",
                "kw_delim": ",",
                "kw_text": "",
            },
            "control": _default_group_cfg(),
            "experimental": _default_group_cfg(),
        }


def _load_widgets_from_store_for_keywords():
    store = st.session_state.ab_setting["keywords"]
    st.session_state.setdefault("kw_method", store.get("kw_method", "텍스트 직접 입력"))
    st.session_state.setdefault("kw_delim", store.get("kw_delim", ","))
    st.session_state.setdefault("kw_text", store.get("kw_text", ""))


def _save_keywords_to_store():
    store = st.session_state.ab_setting["keywords"]
    store["kw_method"] = st.session_state.get("kw_method", "텍스트 직접 입력")
    store["kw_delim"] = st.session_state.get("kw_delim", ",")
    store["kw_text"] = st.session_state.get("kw_text", "")


def _load_widgets_from_store_for_group(prefix: str):
    g = st.session_state.ab_setting[prefix]

    # ✅ FIX: 위젯 키를 store 값으로 "없을 때만" 채움 (사용자 입력을 덮지 않음)
    st.session_state.setdefault(f"{prefix}_method", g.get("method", "GET"))
    st.session_state.setdefault(f"{prefix}_url", g.get("url", ""))
    st.session_state.setdefault(f"{prefix}_param", g.get("param", "query"))
    st.session_state.setdefault(f"{prefix}_headers", g.get("headers", ""))
    st.session_state.setdefault(f"{prefix}_body", g.get("body", ""))
    st.session_state.setdefault(f"{prefix}_parse", g.get("parse", ""))

    st.session_state.setdefault(f"{prefix}_tested", g.get("tested", False))
    st.session_state.setdefault(f"{prefix}_last_curl", g.get("last_curl", ""))
    st.session_state.setdefault(f"{prefix}_last_result", g.get("last_result", None))
    st.session_state.setdefault(f"{prefix}_last_error", g.get("last_error", None))

    # fixed params rows
    fixed_key = f"{prefix}_fixed_params"
    if fixed_key not in st.session_state:
        st.session_state[fixed_key] = g.get("fixed_params_rows", []) or []


def _save_group_widgets_to_store(prefix: str):
    g = st.session_state.ab_setting[prefix]

    g["method"] = st.session_state.get(f"{prefix}_method", "GET")
    g["url"] = st.session_state.get(f"{prefix}_url", "")
    g["param"] = st.session_state.get(f"{prefix}_param", "query")
    g["headers"] = st.session_state.get(f"{prefix}_headers", "")
    g["body"] = st.session_state.get(f"{prefix}_body", "")
    g["parse"] = st.session_state.get(f"{prefix}_parse", "")

    g["tested"] = bool(st.session_state.get(f"{prefix}_tested", False))
    g["last_curl"] = st.session_state.get(f"{prefix}_last_curl", "")
    g["last_result"] = st.session_state.get(f"{prefix}_last_result", None)
    g["last_error"] = st.session_state.get(f"{prefix}_last_error", None)

    fixed_key = f"{prefix}_fixed_params"
    g["fixed_params_rows"] = st.session_state.get(fixed_key, []) or []


def _save_current_step_snapshot():
    # ✅ FIX: 이동/버튼 액션 전에 “현재 입력값”을 store로 스냅샷
    step = st.session_state.current_step
    if step == 1:
        _save_keywords_to_store()
    elif step == 2:
        _save_group_widgets_to_store("control")
    elif step == 3:
        _save_group_widgets_to_store("experimental")

def _parse_keyword_params(raw: str) -> List[str]:
    """
    "query, sparseQuery" / "query sparseQuery" / "query|sparseQuery" 등
    다양한 입력을 받아 키 목록으로 정리
    """
    if not raw:
        return []
    # 콤마/공백/파이프/줄바꿈 지원
    seps = [",", "|", "\n", "\t"]
    s = raw
    for sep in seps:
        s = s.replace(sep, " ")
    keys = [x.strip() for x in s.split(" ") if x.strip()]
    # 중복 제거 (순서 유지)
    seen = set()
    out = []
    for k in keys:
        if k not in seen:
            out.append(k)
            seen.add(k)
    return out

# =====================================================
# Page Entry
# =====================================================
def render():
    _init_state()

    st.title("Test Setting")
    st.caption("검색 키워드 및 대조군(Control Group) / 실험군(Experimental Group) 조건을 단계별로 설정합니다.")
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    _render_stepper(current_step=st.session_state.current_step)
    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    st.markdown("<div style='height:50px'></div>", unsafe_allow_html=True)

    step = st.session_state.current_step
    if step == 0:
        _render_step_intro()
    elif step == 1:
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
def _config_dir() -> Path:
    return Path.cwd() / "test_config"

def _config_path(test_name: str) -> Path:
    safe = test_name.strip()
    return _config_dir() / f"{safe}.json"

def _config_exists(test_name: str) -> bool:
    if not test_name.strip():
        return False
    return _config_path(test_name).exists()

def _init_state():
    if "current_step" not in st.session_state:
        st.session_state.current_step = 0

    # ✅ FIX: store init
    _init_setting_store()

    # ✅ step completion flags (Next gate)
    st.session_state.setdefault("step_2a_completed", False)
    st.session_state.setdefault("step_2b_completed", False)
    st.session_state.setdefault("generation_saved_ok", False)
    st.session_state.setdefault("last_saved_path", "")

    if "generated_payload" not in st.session_state:
        st.session_state.generated_payload = None


def _can_go_next(step: int) -> bool:
    if step == 0:
        name = (st.session_state.ab_setting.get("test_name") or "").strip()
        if not name:
            return False
        # 같은 이름 파일 체크 (아래 2번의 저장 경로 함수 재사용)
        return not _config_exists(name)
    if step == 1:
        return bool(get_keywords())
    if step == 2:
        return bool(st.session_state.step_2a_completed)
    if step == 3:
        return bool(st.session_state.step_2b_completed)
    if step == 4:
        return bool(get_keywords()) and st.session_state.step_2a_completed and st.session_state.step_2b_completed
    return False


def _go_prev():
    _save_current_step_snapshot()
    first_step = STEPS[0]["id"]
    st.session_state.current_step = max(first_step, st.session_state.current_step - 1)

def _go_next():
    _save_current_step_snapshot()
    last_step = STEPS[-1]["id"]
    st.session_state.current_step = min(last_step, st.session_state.current_step + 1)

def _go_done():
    st.session_state.page = "runner"
    # TODO: done 클릭 시 해당 세팅 초기화 후 0번으로 이동되도록 수정.

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
    # ✅ FIX: Next 클릭 시점에도 스냅샷
    _save_current_step_snapshot()

    step = st.session_state.current_step

    if _can_go_next(step):
        _go_next()
        return

    if step == 0:
        msg = "다음 단계로 이동하려면 테스트 이름을 설정 해 주세요."
    elif step == 1:
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

    # ✅ FIX: step id 기반으로 첫/마지막 판단 (len(STEPS)는 6이지만 마지막 id는 5)
    first_step = STEPS[0]["id"]      # 0
    last_step = STEPS[-1]["id"]      # 5

    is_first = (step == first_step)
    is_last = (step == last_step)

    # ✅ Next가 맨 오른쪽, Back이 그 왼쪽
    spacer, c_back, c_next = st.columns([0.78, 0.10, 0.12], gap="small", vertical_alignment="center")

    with c_back:
        st.button("‹ Back", use_container_width=True, disabled=is_first, on_click=_go_prev)

    with c_next:
        if not is_last:
            st.button("Next ›", type="primary", use_container_width=True, on_click=_on_next_clicked)
        else:
            # ✅ 마지막(step 5)에서는 Done 표시 + 저장 완료 시 활성화
            done_enabled = bool(st.session_state.get("generation_saved_ok", False))
            st.button(
                "Done",
                type="primary",
                use_container_width=True,
                disabled=not done_enabled,
                on_click=_go_done
            )

# =====================================================
# STEP 0. Overview
# =====================================================
def _render_step_intro():
    st.markdown("### LLM as a Judge 테스트 설정 개요")
    st.markdown(
        """
        <div style="
            padding: 16px 18px;
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 12px;
            background: rgba(255,255,255,0.03);
            line-height: 1.65;
        ">
          <div style="margin-bottom: 10px;">
            이 테스트는 <b>LLM as a Judge 평가</b>를 수행하기 위해 필요한
            <b>테스트 데이터 수집 설정</b>과 <b>테스트 데이터 생성·저장</b> 전체 과정을 구성하기 위한 설정 페이지입니다.
          </div>

          <div style="margin-bottom: 12px;">
            <b>검색 키워드</b>를 기반으로 <b>Control / Experimental</b> API 호출 조건을 정의하고,
            각 조건에 대해 실제 호출을 수행하여 응답 데이터를 수집합니다.<br/>
            수집된 결과는 이후 LLM 기반 평가에 활용할 수 있도록
            <b>구조화된 테스트 데이터(JSON)</b> 형태로 생성되며, <b>서버 지정 경로</b>에 저장됩니다.
          </div>

          <div style="font-weight: 700; margin: 10px 0 6px;">
            이 설정 과정에서 다루는 항목
          </div>

          <ul style="margin: 0 0 12px 18px; padding: 0;">
            <li><b>검색 키워드</b> 정의</li>
            <li><b>Control / Experimental</b> 그룹별 API 요청 방식 및 파라미터 설정</li>
            <li><b>응답 파싱 규칙</b> 정의</li>
            <li><b>전체 키워드</b>에 대한 테스트 데이터 일괄 생성 및 저장</li>
          </ul>

          <div style="
              padding: 10px 12px;
              border-left: 4px solid rgba(99,102,241,0.9);
              background: rgba(99,102,241,0.10);
              border-radius: 8px;
          ">
            최종적으로 <b>하나의 테스트 설정 이름(name)</b>을 기준으로
            <b>재현 가능한 평가용 데이터셋</b>을 생성하는 것을 목표로 합니다.
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )
    name = st.text_input("테스트 설정 이름", key="test_name_input")
    # 입력 시 store 반영
    st.session_state.ab_setting["test_name"] = name.strip()
    if _config_exists(st.session_state.ab_setting["test_name"]):
        st.error("같은 이름의 테스트 설정이 이미 존재합니다. 다른 이름을 입력하세요.")

# =====================================================
# STEP 1. Keyword
# =====================================================
def _render_step_keywords():
    # ✅ FIX: store -> widgets
    _load_widgets_from_store_for_keywords()

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
                delimiter = st.text_input("구분자", help="예: , | ; 또는 \\n", key="kw_delim")

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
            _save_keywords_to_store()  # ✅ FIX: 버튼 클릭 직전도 저장

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
# Helpers - Config I/O (✅ FIX: now reads from store, not raw widget state)
# =====================================================
def _cfg(prefix: str) -> dict:
    # store를 신뢰 (렌더링/조건부 위젯 영향 없음)
    g = st.session_state.ab_setting[prefix]

    fixed_rows = g.get("fixed_params_rows", []) or []
    fixed_params = {r.get("k"): r.get("v") for r in fixed_rows if (r.get("k") or "").strip()}

    headers_text = g.get("headers", "") or ""
    body_text = g.get("body", "") or ""

    return {
        "method": g.get("method", "GET"),
        "url": g.get("url", ""),
        "keyword_param": g.get("param", "query"),
        "fixed_params": fixed_params,
        "headers": parse_json_string(headers_text) if headers_text else None,
        "base_body": parse_json_string(body_text) if body_text else None,
        "parse_path": g.get("parse", ""),
        "tested": bool(g.get("tested", False)),
        "last_curl": g.get("last_curl", ""),
    }


from typing import List

def _parse_keyword_params(raw: str) -> List[str]:
    """
    "query, sparseQuery" / "query sparseQuery" / "query|sparseQuery" 등
    다양한 입력을 받아 키 목록으로 정리
    """
    if not raw:
        return []
    s = str(raw).strip()

    # 구분자들을 공백으로 통일
    for sep in [",", "|", "\n", "\t"]:
        s = s.replace(sep, " ")

    keys = [x.strip() for x in s.split(" ") if x.strip()]

    # 중복 제거(순서 유지)
    seen = set()
    out = []
    for k in keys:
        if k not in seen:
            out.append(k)
            seen.add(k)
    return out


def _build_request_for_keyword(prefix: str, keyword: str):
    cfg = _cfg(prefix)
    method = cfg["method"]
    url = (cfg["url"] or "").strip()

    # ✅ 기존: keyword_param 문자열 1개
    # keyword_param = cfg["keyword_param"]

    # ✅ 변경: 여러 param 지원
    raw_param = cfg.get("keyword_param", "")
    keyword_params = _parse_keyword_params(raw_param)

    headers = cfg["headers"]
    fixed_params = cfg["fixed_params"] or {}
    base_body = cfg["base_body"] if isinstance(cfg["base_body"], dict) else {}

    # 키워드 파라미터가 비어있으면 fallback (원하면 제거 가능)
    if not keyword_params:
        keyword_params = ["query"]

    if method == "GET":
        # ✅ call_url: fixed_params까지 합친 "기본 호출 url"
        call_url = merge_query_params(url, fixed_params)

        # ✅ curl_url: keyword 파라미터 여러 개를 넣은 "테스트용 curl url"
        kw_params_dict = {kp: keyword for kp in keyword_params}
        curl_url = merge_query_params(call_url, kw_params_dict)

        body = None
        curl = build_curl("GET", curl_url, headers, None)

        # ✅ 반환값의 keyword_param은 '문자열 1개'로 쓰던 흔적이므로
        #    하위 호환을 위해 원본 raw_param 그대로 반환 (또는 "," join)
        return call_url, "GET", raw_param, headers, body, curl

    # POST
    body = dict(base_body)
    body.update(fixed_params)

    # ✅ curl_body: 실제 요청 body에 keyword를 여러 키로 주입
    curl_body = dict(body)
    for kp in keyword_params:
        curl_body[kp] = keyword

    curl = build_curl("POST", url, headers, curl_body)

    # ✅ 마찬가지로 raw_param 그대로 반환
    return url, "POST", raw_param, headers, body, curl


# =====================================================
# STEP 2/3. API
# =====================================================
def _render_step_api(group_name: str, group_prefix: str, step_key: str, step_no: int):
    if not get_keywords():
        st.warning("먼저 검색 키워드를 설정해주세요.")
        return

    # ✅ FIX: store -> widgets (이게 없으면 Prev/Next 복원 안됨)
    _load_widgets_from_store_for_group(group_prefix)

    keywords = get_keywords()
    example_kw = keywords[0] if keywords else ""

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
        st.markdown("**Default Setting**")

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
            help=f"예: query / q / keyword (테스트 예시: {example_kw})\n , 구분자를 통해 동일 키워드를 여러 파라미터에 담을 수 있습니다.",
            key=f"{group_prefix}_param"
        )

        st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

        st.markdown("**Extra Parameters Setting**")
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
                            # ✅ FIX: delete도 저장 반영
                            _save_group_widgets_to_store(group_prefix)
                            st.rerun()

            if st.button("＋ 파라미터 추가", use_container_width=True, key=f"{fixed_rows_key}_add"):
                st.session_state[fixed_rows_key].append({"k": "", "v": ""})
                _save_group_widgets_to_store(group_prefix)  # ✅ FIX
                st.rerun()

        with st.expander("고급 요청 설정", expanded=False):
            st.text_area("HTTP Headers (JSON)", height=90, key=f"{group_prefix}_headers")
            if st.session_state.get(f"{group_prefix}_method", "GET") == "POST":
                st.text_area("기본 Request Body (JSON)", height=110, key=f"{group_prefix}_body")

        st.text_input(
            "테스트 데이터 응답 파싱 경로 (선택)",
            placeholder="예: data.items.0.title",
            key=f"{group_prefix}_parse"
        )

        tested = bool(st.session_state.get(f"{group_prefix}_tested", False))
        st.markdown(
            "<span class='badge done'>테스트 성공</span>" if tested else "<span class='badge todo'>미테스트</span>",
            unsafe_allow_html=True
        )

        if st.button("API 테스트 실행", type="primary", use_container_width=True, key=f"{group_prefix}_test"):
            # ✅ FIX: 테스트 실행 전 현재 입력값을 store로 스냅샷 (5번에서 반드시 필요)
            _save_group_widgets_to_store(group_prefix)

            st.session_state[last_error_key] = None
            st.session_state.ab_setting[group_prefix]["last_error"] = None  # store에도 반영

            cfg = _cfg(group_prefix)
            url = (cfg["url"] or "").strip()
            if not url:
                st.session_state[last_error_key] = "API Endpoint를 입력해주세요."
                st.session_state[f"{group_prefix}_tested"] = False
                _save_group_widgets_to_store(group_prefix)
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
                    if step_key == "2a":
                        st.session_state.step_2a_completed = True
                    elif step_key == "2b":
                        st.session_state.step_2b_completed = True

                    # 외부 세션 매니저가 숫자만 받는 경우도 대비
                    try:
                        set_step_completed(step_no, True)
                    except Exception:
                        pass
                    try:
                        set_step_completed(step_key, True)
                    except Exception:
                        pass
                else:
                    st.session_state[last_error_key] = result.get("error", "호출 실패")

            except Exception as e:
                st.session_state[last_error_key] = str(e)
                st.session_state[f"{group_prefix}_tested"] = False

            # ✅ FIX: 결과/상태 포함해서 store에 저장
            _save_group_widgets_to_store(group_prefix)
            st.rerun()

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
# STEP 4. Review
# =====================================================
def _render_step_review():
    # ✅ FIX: Review 진입 시점에 마지막 스냅샷 (2/3에서 입력하고 바로 Next로 온 경우도 안전)
    _save_current_step_snapshot()

    left, right = st.columns([0.42, 0.58], gap="large", vertical_alignment="top")

    with left:
        st.markdown("<div class='step-title'>4. Review</div>", unsafe_allow_html=True)
        st.markdown("<div class='sub'>현재 설정된 키워드/그룹 설정을 최종 확인합니다.</div>", unsafe_allow_html=True)

    with right:
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
    # ✅ FIX: Generation도 진입 시점에 스냅샷
    _save_current_step_snapshot()

    # 상태 초기화
    st.session_state.setdefault("entered_step5", False)
    if not st.session_state.entered_step5:
        st.session_state.generation_saved_ok = False
        st.session_state.last_saved_path = ""
        st.session_state.entered_step5 = True

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

        if not (st.session_state.step_2a_completed and st.session_state.step_2b_completed):
            st.warning("Control/Experimental 설정을 완료(테스트 성공)한 뒤에 생성할 수 있습니다.")
            return

        # ✅ FIX: 여기서도 store 기반 config를 다시 읽어 검증 가능
        control_cfg = _cfg("control")
        exp_cfg = _cfg("experimental")

        if not (control_cfg.get("url") and exp_cfg.get("url")):
            st.error("Control/Experimental Endpoint가 비어있습니다. Step 2/3 설정을 확인해주세요.")
            return

        st.markdown("### Generate")
        st.caption(f"총 {len(kws)}개 키워드를 Control/Experimental로 모두 호출합니다.")

        run = st.button("테스트 데이터 생성", type="primary", use_container_width=True)
        gen_notice = st.empty()
        if run:
            progress = st.progress(0)
            status = st.empty()

            results = []
            total = len(kws)

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
                # row["control"]["raw"] = c_res.get("data") if c_res.get("success") else None

                c_parse = control_cfg.get("parse_path") or ""
                if c_res.get("success"):
                    if c_parse:
                        try:
                            row["control"]["result"] = parse_json_path(c_res.get("data"), c_parse)
                        except Exception as e:
                            row["control"]["parsed_error"] = str(e)
                    else:
                        row["control"]["result"] = c_res.get("data")

                # Experimental
                e_url, e_method, e_kp, e_headers, e_body, e_curl = _build_request_for_keyword("experimental", kw)
                e_res = make_api_call(e_url, e_method, kw, e_kp, e_headers, e_body)

                row["experimental"]["curl"] = e_curl
                row["experimental"]["success"] = bool(e_res.get("success"))
                row["experimental"]["status"] = e_res.get("status")
                row["experimental"]["error"] = e_res.get("error")
                # row["experimental"]["raw"] = e_res.get("data") if e_res.get("success") else None

                e_parse = exp_cfg.get("parse_path") or ""
                if e_res.get("success"):
                    if e_parse:
                        try:
                            row["experimental"]["result"] = parse_json_path(e_res.get("data"), e_parse)
                        except Exception as e:
                            row["experimental"]["parsed_error"] = str(e)
                    else:
                        row["experimental"]["result"] = e_res.get("data")

                results.append(row)
                progress.progress(idx / total)

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

            # 실행 완료 여부 설정
            control_fail = sum(1 for r in results if not r["control"].get("success"))
            exp_fail = sum(1 for r in results if not r["experimental"].get("success"))
            any_fail = (control_fail > 0) or (exp_fail > 0)

            if any_fail:
                gen_notice.warning(
                    f"생성 완료(부분 실패 포함). Control 실패 {control_fail}건 / Experimental 실패 {exp_fail}건"
                )
            else:
                gen_notice.success("완료! 모든 키워드에 대해 Control/Experimental 테스트 데이터가 생성되었습니다.")

            # config 데이터 저장
            test_name = st.session_state.ab_setting.get("test_name", "").strip()
            if not test_name:
                st.error("테스트 설정 이름이 없습니다. 처음 단계로 돌아가 이름을 설정해주세요.")
                return

            out_dir = _config_dir()
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = _config_path(test_name)

            out_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

            st.session_state.generated_payload = payload  # 내부 보관은 해도 되고 안 해도 됨
            st.toast(f"저장 완료: {out_path}", icon="✅")
            st.session_state.generation_saved_ok = True  # ✅ 추가
            st.session_state.last_saved_path = str(out_path)
            st.rerun()

        if st.session_state.get("generated_payload"):
            st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
            st.markdown("### Output")

            # ✅ 저장 완료 안내 텍스트(고정)
            saved_path = st.session_state.get("last_saved_path", "")
            if saved_path:
                st.info(
                    f"✅ 설정 JSON이 아래 위치에 저장 완료되었습니다.\n\n"
                    f"- 저장 경로: `{saved_path}`\n\n"
                    f"다른 위치에 저장하려면 아래에서 경로/파일명을 지정해 저장하세요."
                )

            # ✅ 다른 위치 저장 UI (접기/펼치기)
            st.session_state.setdefault("show_alt_save", False)

            if not st.session_state.show_alt_save:
                # 기본 상태: 버튼만 노출
                if st.button("서버에 다른 위치로 저장", use_container_width=True, key="open_alt_save"):
                    st.session_state.show_alt_save = True
                    st.rerun()
            else:
                # 펼쳐진 상태: 입력 + 저장 버튼만 노출
                st.markdown("#### 다른 위치로 저장")

                default_dir = str(_config_dir())
                alt_dir = st.text_input("저장 폴더(서버 경로)", value=default_dir, key="alt_save_dir")

                test_name = st.session_state.ab_setting.get("test_name", "").strip() or "test_config"
                alt_file = st.text_input("파일명", value=f"{test_name}.json", key="alt_save_name")

                save_notice = st.empty()

                c_cancel, c_save = st.columns([0.35, 0.65], gap="small")
                with c_cancel:
                    if st.button("취소", use_container_width=True, key="close_alt_save"):
                        st.session_state.show_alt_save = False
                        st.rerun()

                with c_save:
                    if st.button("저장", type="primary", use_container_width=True, key="do_alt_save"):
                        try:
                            from pathlib import Path
                            out_dir2 = Path(alt_dir)
                            out_dir2.mkdir(parents=True, exist_ok=True)

                            filename = alt_file.strip()
                            if not filename.lower().endswith(".json"):
                                filename += ".json"

                            out_path2 = out_dir2 / filename
                            out_path2.write_text(
                                json.dumps(st.session_state.generated_payload, ensure_ascii=False, indent=2),
                                encoding="utf-8"
                            )

                            save_notice.success(f"✅ 저장 완료: {out_path2}")
                            st.session_state.generation_saved_ok = True
                            st.session_state.last_saved_path = str(out_path2)

                            # 저장 성공하면 접기(원하면 유지해도 됨)
                            st.session_state.show_alt_save = False
                            st.rerun()

                        except Exception as e:
                            save_notice.error(f"저장 실패: {e}")