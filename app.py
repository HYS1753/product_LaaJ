import streamlit as st
from _pages import readme_page, test_config_page, test_result_page
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

# -----------------------------
# Global CSS (FINAL CLEAN)
# -----------------------------
st.markdown("""
<style>

/* =========================
   Global
========================= */
html, body {
    font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", sans-serif;
}

/* =========================
   App Background (PURE WHITE)
========================= */
[data-testid="stAppViewContainer"] {
    background: #ffffff;
}

/* =========================
   Main Content
========================= */
[data-testid="stMainBlockContainer"] {
    background: transparent !important;
}

/* =========================
   Header (Thin Glass Bar)
========================= */
[data-testid="collapsedControl"] {
    display: none;
}

[data-testid="stHeader"] {
    height: 52px;
    background: rgba(255,255,255,0.55);
    backdrop-filter: blur(18px);
    -webkit-backdrop-filter: blur(18px);
    border-bottom: 0.5px solid rgba(0,0,0,0.05);
}

/* =========================
   Sidebar Base
========================= */
[data-testid="stSidebar"] {
    background: transparent;
    padding: 20px 14px;
}

/* =========================
   Sidebar Header
========================= */
.sidebar-header {
    padding: 12px 14px 18px 14px;
    margin-bottom: 8px;
}

.app-title {
    font-size: 17px;
    font-weight: 800;
    letter-spacing: -0.01em;
    color: rgba(30,35,40,0.95);
}

.app-subtitle {
    font-size: 12px;
    color: rgba(30,35,40,0.55);
    margin-top: 2px;
}

/* =========================
   Sidebar Floating Panel
========================= */
[data-testid="stSidebar"] > div:first-child {
    background:
        radial-gradient(900px 500px at 10% -10%, rgba(180,200,255,0.25), transparent 60%),
        radial-gradient(700px 400px at 90% 10%, rgba(255,180,200,0.18), transparent 55%),
        linear-gradient(180deg, #f7f8fb 0%, #eef1f6 100%);
    backdrop-filter: blur(28px) saturate(160%);
    -webkit-backdrop-filter: blur(28px) saturate(160%);
    border-radius: 22px;
    padding: 18px 14px;
    border: 0.5px solid rgba(255,255,255,0.7);
    box-shadow:
        0 18px 36px rgba(0,0,0,0.12),
        inset 0 1px 0 rgba(255,255,255,0.6);
}

/* =========================
   Sidebar Ratios
========================= */
/* hide radio circle */
[data-testid="stRadio"] div[role="radiogroup"] > label > div:first-child {
    display: none;
}

/* label wrapper */
[data-testid="stRadio"] label {
    width: 100%;
    cursor: pointer;
}

/* 실제 버튼 영역 */
[data-testid="stRadio"] label > div {
    width: 100%;
    padding: 10px 14px;
    border-radius: 14px;
    font-size: 14px;
    line-height: 1.4;
    transition: all 0.25s ease;
}

/* hover */
[data-testid="stRadio"] label:hover > div {
    background: rgba(255,255,255,0.4);
}

/* active */
[data-testid="stRadio"] input:checked + div {
    background:
        linear-gradient(
            180deg,
            rgba(255,255,255,0.65),
            rgba(255,255,255,0.45)
        );
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,0.6),
        0 4px 12px rgba(0,0,0,0.08);
    font-weight: 600;
}

/* =========================
   Cards (Liquid Surface)
========================= */
.card {
    background:
        linear-gradient(
            135deg,
            rgba(255,255,255,0.75),
            rgba(255,255,255,0.55)
        );
    backdrop-filter: blur(22px) saturate(160%);
    border-radius: 20px;
    padding: 28px;
    border: 0.5px solid rgba(0,0,0,0.06);
    box-shadow:
        0 12px 32px rgba(0,0,0,0.08);
}

/* 섹션 컨테이너 */
.section-card {
    background: white;
    border: 1px solid var(--border-light);
    border-radius: 10px;
    padding: 20px;
}

/* 상태 배지 */
.status-badge {
    margin-top: 28px;
    padding: 6px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 600;
    text-align: center;
}

.status-done {
    background: var(--success-soft);
    color: #256f3a;
}

.status-pending {
    background: #f3f4f6;
    color: var(--text-muted);
}

/* 설명 텍스트 */
.helper-text {
    color: var(--text-muted);
    font-size: 14px;
    line-height: 1.6;
}

</style>
""", unsafe_allow_html=True)

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