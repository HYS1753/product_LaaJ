import json
import re
from typing import Any

def unwrap_markdown(text: str) -> str:
    """
    모델 출력이 아래 케이스로 와도 '마크다운 본문'만 뽑아냄.
    - {"result": "..."} 또는 {"report_md": "..."} 등 JSON wrapper
    - ``` / ~~~ 코드펜스로 감싼 케이스
    - 앞뒤 공백/따옴표/잡다한 프리픽스
    """
    if not text:
        return ""

    s = text.strip()

    # 1) 코드펜스 제거 (```...``` 또는 ~~~...~~~)
    #    - 맨 바깥이 펜스로 감싸진 경우만 제거
    fence = re.match(r"^\s*(```|~~~)\w*\s*\n([\s\S]*?)\n\1\s*$", s)
    if fence:
        s = fence.group(2).strip()

    # 2) JSON wrapper 제거 시도
    #    - '{'로 시작하면 JSON일 가능성이 높음
    if s.startswith("{"):
        try:
            obj: Any = json.loads(s)
            if isinstance(obj, dict):
                # 흔히 쓰는 키 우선순위
                for k in ("report_md", "result", "markdown", "md", "content", "text"):
                    if k in obj and isinstance(obj[k], str):
                        return obj[k].strip()

                # dict인데 값 중 문자열이 하나만 있으면 그것 사용
                str_vals = [v for v in obj.values() if isinstance(v, str)]
                if len(str_vals) == 1:
                    return str_vals[0].strip()
        except Exception:
            pass

    # 3) 그래도 남아있으면 그냥 원문 반환
    return s