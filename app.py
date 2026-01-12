import streamlit as st
from _pages import readme_page, test_setting_page, test_runner_page
from utils.css_loader import load_css
from utils.session_manager import init_session_state
from dotenv import load_dotenv

# -----------------------------
# Environment Load
# -----------------------------
load_dotenv()

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
        "css/components_kpis.css",
        "css/components_summary_cards.css",
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
        ["description", "setting", "runner"],  # 🔴 내부 값 = state 값
        label_visibility="collapsed",
        key="page",  # 🔴 기존 state 그대로 사용
        format_func=lambda x: {
            "description": "📖ㅤDescription",
            "setting": "⚙️ㅤTest Setting",
            "runner": "🚀ㅤTest Runner", # 📊
        }[x],
    )

# -----------------------------
# Page Routing
# -----------------------------
if st.session_state.page == "description":
    readme_page.render()
elif st.session_state.page == "setting":
    test_setting_page.render()
elif st.session_state.page == "runner":
    test_runner_page.render()