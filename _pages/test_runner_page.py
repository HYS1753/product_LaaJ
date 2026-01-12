import json
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
    st.session_state.page = "setting"

# -------------------------
# Page
# -------------------------
def render():
    st.title("Test Runner")
    st.caption("저장된 테스트 설정을 선택하고 테스트를 실행합니다.")
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

    base_dir = _config_dir()
    base_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------
    # Load list
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
        "테스트 수행 할 설정을 선택한 뒤 <b>Run Test</b> 버튼을 통해 다음 단계에서 실행 로직을 연결할 수 있습니다."
        "<br>"
        "또한, <b>➕ 새 테스트 만들기</b> 버튼으로 설정을 추가 할 수 있습니다."
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

    # -------------------------
    # Empty state
    # -------------------------
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

    # -------------------------
    # State init (single source of truth)
    # -------------------------
    st.session_state.setdefault("selected_test_config_path", None)
    st.session_state.setdefault("detail_open", False)
    st.session_state.setdefault("delete_confirm_open", False)

    # -------------------------
    # Layout row: KPI | List
    # -------------------------
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
        # -------------------------
        # Grid (single selection)
        # -------------------------
        df = pd.DataFrame(rows, columns=["Name", "Created", "path", "mtime"])

        gb = GridOptionsBuilder.from_dataframe(df)
        gb.configure_default_column(sortable=True, filter=True, resizable=True)

        # ✅ single select checkbox
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
            key="test_config_grid_simple",  # ✅ key 고정
        )

        # selected_rows 타입 다양성 대응
        picked_path = None
        selected_rows = grid_response.get("selected_rows", [])
        if isinstance(selected_rows, list) and selected_rows:
            picked_path = selected_rows[0].get("path")
        elif isinstance(selected_rows, pd.DataFrame) and not selected_rows.empty:
            picked_path = selected_rows.iloc[0].get("path")

        st.session_state.selected_test_config_path = picked_path
        selected_name = Path(picked_path).stem if picked_path else None

        # -------------------------
        # Actions bar (grid 아래)
        # -------------------------
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # -------------------------
        # Run mock (유지)
        # -------------------------
        run_disabled = st.session_state.selected_test_config_path is None

        if st.button(
            "▶ Run Test (목업)",
            type="primary",
            use_container_width=True,
            disabled=run_disabled,
            key="run_mock_btn",
        ):
            st.toast(
                f"선택된 설정: {Path(st.session_state.selected_test_config_path).name}",
                icon="🧪",
            )