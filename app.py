import streamlit as st
from _pages import readme_page, test_config_page, test_result_page
from utils.css_loader import load_css
from utils.session_manager import init_session_state

# -----------------------------
# Page Config
# -----------------------------
st.set_page_config(
    page_title="LLM as a Judge",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ------------------------------
# CSS Load
# ------------------------------
load_css(
        "css/tokens.css",
        "css/global.css",
        "css/layout_header_sidebar.css",
        "css/components_cards_badges.css",
        "css/components_stepper_wizard.css",
        "css/components_buttons.css",
        "css/components_kpis.css"
    )

# -----------------------------
# Session State
# -----------------------------
init_session_state()

# -----------------------------
# Sidebar Navigation
# -----------------------------
with st.sidebar:
    st.markdown("""
        <div class="sidebar-header">
            <div class="app-title">⚖️ LLM as a Judge</div>
            <div class="app-subtitle">Evaluation Dashboard</div>
        </div>
    """, unsafe_allow_html=True)

    page = st.radio(
        "navigation",
        ["description", "settings", "run&result"],  # 🔴 내부 값 = state 값
        label_visibility="collapsed",
        key="page",  # 🔴 기존 state 그대로 사용
        format_func=lambda x: {
            "description": "📖ㅤDescription",
            "settings": "⚙️ㅤTest Settings",
            "run&result": "📊ㅤTest Run & Result",
        }[x],
    )

# -----------------------------
# Page Routing
# -----------------------------
if st.session_state.page == "description":
    readme_page.render()
elif st.session_state.page == "settings":
    test_config_page.render()
elif st.session_state.page == "run&result":
    test_result_page.render()