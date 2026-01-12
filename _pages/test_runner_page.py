import json
import time
import html
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode


# -------------------------
# Paths / utils
# -------------------------
def _config_dir() -> Path:
    return Path.cwd() / "test_config"


def _fmt_dt(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "-"


def _goto_setting():
    # ⚠️ app 라우팅 키에 맞춰 수정 필요할 수 있음
    st.session_state.page = "setting"
    st.rerun()

def _json_pretty(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)

def _read_json(path: str) -> dict:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))

def _preview_value(v):
    """리스트/딕트/스칼라를 '미리보기 1개 + 외 n개' 형태로 정리"""
    if isinstance(v, list):
        if len(v) == 0:
            return {"preview": None, "more": 0}
        return {"preview": v[0], "more": max(0, len(v) - 1)}
    return {"preview": v, "more": 0}

def _make_summary(payload: dict) -> dict:
    meta = payload.get("meta", {}) or {}
    keywords = payload.get("keywords", []) or []

    control = payload.get("control_config", {}) or {}
    exp = payload.get("experimental_config", {}) or {}

    results = payload.get("results", []) or []
    c_ok = c_fail = e_ok = e_fail = 0

    control_preview_item = None
    experimental_preview_item = None
    control_preview_total = 0
    experimental_preview_total = 0

    for i, r in enumerate(results):
        c = (r.get("control") or {})
        e = (r.get("experimental") or {})

        if c.get("success") is True:
            c_ok += 1
        elif c.get("success") is False:
            c_fail += 1

        if e.get("success") is True:
            e_ok += 1
        elif e.get("success") is False:
            e_fail += 1

        # ✅ 첫 row 기준 preview: 리스트면 1개만, 나머지는 ...외 N개
        if i == 0:
            c_items = c.get("result")
            e_items = e.get("result")

            if isinstance(c_items, list) and len(c_items) > 0:
                control_preview_item = c_items[0]
                control_preview_total = max(0, len(c_items))
            else:
                control_preview_item = c_items  # dict/str/None 그대로

            if isinstance(e_items, list) and len(e_items) > 0:
                experimental_preview_item = e_items[0]
                experimental_preview_total = max(0, len(e_items))
            else:
                experimental_preview_item = e_items

    return {
        "generated_at": meta.get("generated_at"),
        "keyword_count": meta.get("keyword_count", len(keywords)),
        "keywords_preview": keywords[:10],

        "control": {
            "method": control.get("method"),
            "url": control.get("url"),
            "keyword_param": control.get("keyword_param"),
            "parse_path": control.get("parse_path"),
            "tested": bool(control.get("tested", False)),
        },
        "experimental": {
            "method": exp.get("method"),
            "url": exp.get("url"),
            "keyword_param": exp.get("keyword_param"),
            "parse_path": exp.get("parse_path"),
            "tested": bool(exp.get("tested", False)),
        },

        "results_count": len(results),
        "control_ok": c_ok,
        "control_fail": c_fail,
        "experimental_ok": e_ok,
        "experimental_fail": e_fail,

        # ✅ preview (카드 내부에서 st.json으로 렌더링할 값)
        "control_preview_item": _json_pretty(control_preview_item),
        "control_preview_total": control_preview_total,
        "experimental_preview_item": _json_pretty(experimental_preview_item),
        "experimental_preview_total": experimental_preview_total,
    }


# -------------------------
# Runner stepper UI
# -------------------------
RUNNER_STEPS = [
    {"id": 1, "label": "Review & Confirm"},
    {"id": 2, "label": "Running"},
    {"id": 3, "label": "Done"},
]


def _render_runner_stepper(current_step: int):
    items = []
    for s in RUNNER_STEPS:
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
        html.append(
            f"""
            <div class='step {state}'>
              <div class='circle'>{sid}</div>
              <div class='label'>{label}</div>
            </div>
            """
        )
        if i != len(items) - 1:
            html.append("<div class='dash-line'></div>")
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


# -------------------------
# Wizard state helpers
# -------------------------
def _init_runner_state():
    st.session_state.setdefault("runner_mode", "list")   # "list" | "wizard"
    st.session_state.setdefault("runner_step", 1)        # 1,2,3
    st.session_state.setdefault("runner_selected_path", None)
    st.session_state.setdefault("runner_confirm_ok", False)
    st.session_state.setdefault("runner_job_done", False)
    st.session_state.setdefault("runner_job_log", "")


def _start_wizard():
    st.session_state.runner_mode = "wizard"
    st.session_state.runner_step = 1
    st.session_state.runner_confirm_ok = False
    st.session_state.runner_job_done = False
    st.session_state.runner_job_log = ""
    #st.rerun()


def _back_to_list():
    st.session_state.runner_mode = "list"
    st.session_state.runner_step = 1
    st.session_state.runner_confirm_ok = False
    st.session_state.runner_job_done = False
    st.session_state.runner_job_log = ""
    st.rerun()


def _go_step(step: int):
    st.session_state.runner_step = step
    st.rerun()


def _go_result_page_mock():
    # TODO: 실제 result 페이지 키로 연결
    # 예) st.session_state.page = "run&result" or "result"
    st.toast("결과 페이지로 이동(목업) — 라우팅 연결 포인트입니다.", icon="✅")


# -------------------------
# Step 1/2/3 screens
# -------------------------
def _render_step1_review():
    st.markdown("<div class='step-title'>1. Review & Confirm</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub'>선택한 테스트 설정(JSON)의 핵심 정보를 확인하고 실행 여부를 선택합니다.</div>", unsafe_allow_html=True)
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

    path = st.session_state.runner_selected_path
    if not path:
        st.error("선택된 테스트 설정이 없습니다. 목록으로 돌아가 다시 선택해주세요.")
        st.button("← Back", on_click=_back_to_list)
        return

    # load json
    try:
        payload = _read_json(path)
        summary = _make_summary(payload)
    except Exception as e:
        st.error(f"설정 JSON을 읽지 못했습니다: {e}")
        st.button("← Back", on_click=_back_to_list)
        return

    name = Path(path).stem

    # Summary card
    st.markdown(
        f"""
        <div class="summary-card">
          <div class="summary-card-head">
            <div>
              <div class="summary-title">{name}</div>
              <div class="summary-sub">Generated at <b>{summary["generated_at"]}</b></div>
            </div>
            <div class="summary-pill">Ready</div>
          </div>

          <div class="summary-grid">
            <div class="summary-box">
              <div class="summary-box-title">Control</div>
              <div class="summary-kv"><b>Method</b> {summary["control"]["method"]}</div>
              <div class="summary-kv"><b>URL</b> {summary["control"]["url"]}</div>
              <div class="summary-kv"><b>Param</b> {summary["control"]["keyword_param"]}</div>
              <div class="summary-kv"><b>Parse</b> {summary["control"]["parse_path"]}</div>
              <div class="summary-kv"><b>Tested</b> {"✅" if summary["control"]["tested"] else "⚠️"}</div>
            </div>
            <div class="summary-box">
              <div class="summary-box-title">Experimental</div>
              <div class="summary-kv"><b>Method</b> {summary["experimental"]["method"]}</div>
              <div class="summary-kv"><b>URL</b> {summary["experimental"]["url"]}</div>
              <div class="summary-kv"><b>Param</b> {summary["experimental"]["keyword_param"]}</div>
              <div class="summary-kv"><b>Parse</b> {summary["experimental"]["parse_path"]}</div>
              <div class="summary-kv"><b>Tested</b> {"✅" if summary["experimental"]["tested"] else "⚠️"}</div>
            </div>
          </div>

          <div class="summary-meta">
            <div class="summary-meta-item"><b>Keyword Count: </b> {summary["keyword_count"]}</div>
            <div class="summary-meta-item"><b>Results: </b> {summary["results_count"]}</div>
            <div class="summary-meta-item">
              <b>Success: </b>
              Control - {summary["control_ok"]}/{summary["results_count"]} |
              Experimental - {summary["experimental_ok"]}/{summary["results_count"]}
            </div>
          </div>

          <div class="summary-preview-row">
            <div class="summary-preview">
              <div class="summary-preview-title">Keywords (preview)</div>
              <div class="summary-preview-body">{", ".join(summary["keywords_preview"]) if summary["keywords_preview"] else "-"}</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ✅ 팝업 상태
    st.session_state.setdefault("open_control_preview", False)
    st.session_state.setdefault("open_experimental_preview", False)

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

    c1, c2 = st.columns([0.5, 0.5])
    with c1:
        if st.button("Control data preview", disabled=(summary.get("control_preview_item") is None), use_container_width=True):
            st.session_state.open_control_preview = True
    with c2:
        if st.button("Experimental data preview", disabled=(summary.get("experimental_preview_item") is None),
                     use_container_width=True):
            st.session_state.open_experimental_preview = True

    # ✅ Control dialog
    if st.session_state.open_control_preview:
        if hasattr(st, "dialog"):
            @st.dialog("Control data preview (1개)")
            def _dlg_c():
                st.json(summary["control_preview_item"])

            _dlg_c()
        else:
            with st.expander("Control data preview (1개)", expanded=True):
                st.json(summary["control_preview_item"])
        st.session_state.open_control_preview = False

    # ✅ Experimental dialog
    if st.session_state.open_experimental_preview:
        if hasattr(st, "dialog"):
            @st.dialog("Experimental 결과 예시 (1개)")
            def _dlg_e():
                st.json(summary["experimental_preview_item"])

            _dlg_e()
        else:
            with st.expander("Experimental 결과 예시 (1개)", expanded=True):
                st.json(summary["experimental_preview_item"])
        st.session_state.open_experimental_preview = False

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    st.checkbox(
        "위 설정으로 테스트를 실행할게요.",
        key="runner_confirm_ok",
    )

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

    c1, c2, c3 = st.columns([0.78, 0.10, 0.12], gap="small", vertical_alignment="center")
    with c1:
        st.caption("")
    with c2:
        st.button("← Back", use_container_width=True, on_click=_back_to_list)
    with c3:
        st.button(
            "Next ›",
            type="primary",
            use_container_width=True,
            disabled=not st.session_state.runner_confirm_ok,
            on_click=lambda: _go_step(2),
        )


def _render_step2_running():
    st.markdown("<div class='step-title'>2. Running</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub'>테스트를 실행하는 단계입니다. 현재는 목업으로 진행도를 표시합니다.</div>", unsafe_allow_html=True)
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

    # 이미 완료 상태면 3단계로
    if st.session_state.runner_job_done:
        _go_step(3)
        return

    # 실행 UI
    st.info("⏳ 테스트 실행 중... (목업)")

    progress = st.progress(0)
    log = st.empty()

    # 목업 진행 (tqdm 느낌)
    steps = 30
    for i in range(steps):
        time.sleep(0.05)
        pct = int(((i + 1) / steps) * 100)
        progress.progress((i + 1) / steps)
        log.markdown(f"<div class='sub'>Running… <b>{pct}%</b></div>", unsafe_allow_html=True)

    st.session_state.runner_job_done = True
    st.session_state.runner_job_log = "Mock run completed successfully."
    st.toast("실행 완료(목업)", icon="✅")

    # ✅ 완료되면 자동으로 3단계로
    _go_step(3)


def _render_step3_done():
    st.markdown("<div class='step-title'>3. Done</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub'>테스트 실행이 완료되었습니다. 결과 페이지로 이동할 수 있습니다.</div>", unsafe_allow_html=True)
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

    name = Path(st.session_state.runner_selected_path).stem if st.session_state.runner_selected_path else "-"

    st.success(f"✅ 테스트 실행 완료 — **{name}**")
    st.markdown(
        """
        <div class="section-card" style="border-radius:14px;">
          <div style="font-size:13px; color:rgba(30,35,40,0.70); line-height:1.6;">
            실행 결과를 확인하려면 <b>결과 페이지</b>로 이동하세요.<br/>
            (현재 단계는 목업이며, 이후 실제 실행 로직과 결과 렌더링을 연결합니다.)
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    c1, c2, c3 = st.columns([0.25, 0.45, 0.30], vertical_alignment="center")
    with c1:
        st.button("← Back", use_container_width=True, on_click=_back_to_list)
    with c2:
        st.caption("결과 페이지 라우팅 키를 연결하면 바로 이동하도록 만들 수 있어요.")
    with c3:
        st.button(
            "결과 페이지로 이동",
            type="primary",
            use_container_width=True,
            on_click=_go_result_page_mock,
        )


# -------------------------
# Page
# -------------------------
def render():
    _init_runner_state()

    st.title("Test Runner")
    st.caption("저장된 테스트 설정을 선택하고 테스트를 실행합니다.")
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

    base_dir = _config_dir()
    base_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------
    # Wizard mode
    # -------------------------
    if st.session_state.runner_mode == "wizard":
        _render_runner_stepper(st.session_state.runner_step)
        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

        if st.session_state.runner_step == 1:
            _render_step1_review()
        elif st.session_state.runner_step == 2:
            _render_step2_running()
        else:
            _render_step3_done()
        return

    # -------------------------
    # List mode (기존 UI 유지 + Run Test로 wizard 진입)
    # -------------------------
    files = sorted(base_dir.glob("*.json"))
    rows = []
    for p in files:
        stat = p.stat()
        rows.append(
            {
                "Name": p.stem,
                "Created": _fmt_dt(stat.st_mtime),
                "path": str(p),
                "mtime": stat.st_mtime,
            }
        )

    count = len(rows)
    latest_ts = max((r["mtime"] for r in rows), default=None)
    latest_str = _fmt_dt(latest_ts) if latest_ts else "-"

    st.markdown("<div class='step-title'>Test Setting Lists</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='sub'>"
        "<br>"
        "<b>Test Setting</b>에서 정의한 테스트 설정 목록 입니다."
        "<br>"
        "테스트 수행 할 설정을 선택한 뒤 <b>Run Test</b> 버튼을 통해 실행 플로우로 진입할 수 있습니다."
        "<br>"
        "또한, <b>➕ 새 테스트 만들기</b> 버튼으로 설정을 추가 할 수 있습니다."
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

    # Empty state
    if count == 0:
        left, right = st.columns([0.75, 0.25], vertical_alignment="center")
        with left:
            st.info("저장된 테스트 설정이 없습니다. 새 테스트 설정을 생성해 주세요.")
        with right:
            st.button(
                "➕ 새 테스트 만들기",
                type="secondary",
                use_container_width=True,
                key="create_new_test_empty",
                on_click=_goto_setting,
            )
        return

    # Layout row: KPI | List
    c_kpi, c_list = st.columns([2, 8], gap="large", vertical_alignment="top")

    with c_kpi:
        st.markdown(
            f"""
            <div class="kpi-kpi-wrap">
              <div class="kpi-kpi-card">
                <div class="kpi-kpi-label">저장된 설정 수</div>
                <div class="kpi-kpi-value">{count}</div>
              </div>
              <div class="kpi-kpi-card">
                <div class="kpi-kpi-label">최근 생성</div>
                <div class="kpi-kpi-value-sm">{latest_str}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("<div style='height:15px'></div>", unsafe_allow_html=True)

        st.button(
            "➕ 새 테스트 만들기",
            type="secondary",
            use_container_width=True,
            key="create_new_test",
            on_click=_goto_setting,
        )

    with c_list:
        df = pd.DataFrame(rows, columns=["Name", "Created", "path", "mtime"])

        gb = GridOptionsBuilder.from_dataframe(df)
        gb.configure_default_column(sortable=True, filter=True, resizable=True)

        gb.configure_selection(selection_mode="single", use_checkbox=True)
        gb.configure_column("Name", headerName="Name", width=520, checkboxSelection=True)
        gb.configure_column("Created", headerName="Created", width=180)
        gb.configure_column("path", hide=True)
        gb.configure_column("mtime", hide=True)

        gb.configure_pagination(enabled=True, paginationAutoPageSize=False, paginationPageSize=5)

        grid_options = gb.build()
        grid_options["suppressRowClickSelection"] = False
        grid_options["rowSelection"] = "single"

        grid_response = AgGrid(
            df,
            gridOptions=grid_options,
            height=303,
            data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
            update_mode=GridUpdateMode.SELECTION_CHANGED,
            fit_columns_on_grid_load=True,
            theme="balham",
            key="test_config_grid_simple",
        )

        picked_path = None
        selected_rows = grid_response.get("selected_rows", [])
        if isinstance(selected_rows, list) and selected_rows:
            picked_path = selected_rows[0].get("path")
        elif isinstance(selected_rows, pd.DataFrame) and not selected_rows.empty:
            picked_path = selected_rows.iloc[0].get("path")

        st.session_state.selected_test_config_path = picked_path

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        run_disabled = st.session_state.selected_test_config_path is None

        def _on_run_clicked():
            # 선택된 설정을 wizard로 넘김
            st.session_state.runner_selected_path = st.session_state.selected_test_config_path
            _start_wizard()

        st.button(
            "▶ Run Test",
            type="primary",
            use_container_width=True,
            disabled=run_disabled,
            key="run_test_btn",
            on_click=_on_run_clicked if not run_disabled else None,
        )