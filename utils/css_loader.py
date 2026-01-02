from pathlib import Path
import streamlit as st


def load_css(*relative_paths: str) -> None:
    """
    여러 CSS 파일을 읽어서 한 번에 <style>로 주입합니다.

    사용 예)
      load_css(
        "css/00_tokens.css",
        "css/10_global.css",
      )
    """
    css_chunks = []

    for rel in relative_paths:
        path = Path(rel)

        if not path.exists():
            raise FileNotFoundError(f"[load_css] CSS file not found: {path.resolve()}")

        css_chunks.append(path.read_text(encoding="utf-8"))

    st.markdown("<style>\n" + "\n\n".join(css_chunks) + "\n</style>", unsafe_allow_html=True)