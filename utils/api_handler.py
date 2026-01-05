import requests
import json
from typing import Dict, Any, Optional
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse


def make_api_call(
        url: str,
        method: str,
        keyword: str,
        keyword_param: str,
        headers: Optional[Dict] = None,
        body_params: Optional[Dict] = None
) -> Dict[str, Any]:
    '''API 호출 실행'''
    try:
        if method == "GET":
            params = {keyword_param: keyword}
            response = requests.get(url, params=params, headers=headers, timeout=10)
        else:  # POST
            body = body_params.copy() if body_params else {}
            body[keyword_param] = keyword
            response = requests.post(url, json=body, headers=headers, timeout=10)

        response.raise_for_status()
        return {
            "success": True,
            "data": response.json(),
            "status": response.status_code
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "status": None
        }


def parse_json_path(data: Any, path: str) -> Any:
    '''JSON 경로로 데이터 파싱 (예: 'data.results.0.title')'''
    try:
        keys = path.split('.')
        result = data
        for key in keys:
            if key.isdigit():
                result = result[int(key)]
            else:
                result = result[key]
        return result
    except:
        return None


def parse_json_string(json_str: str) -> Optional[Dict]:
    '''JSON 문자열 파싱 (에러 처리 포함)'''
    try:
        return json.loads(json_str)
    except:
        return None

def merge_query_params(url: str, extra_params: dict) -> str:
    """url에 query param을 병합해서 반환"""
    if not extra_params:
        return url
    u = urlparse(url)
    q = dict(parse_qsl(u.query, keep_blank_values=True))
    # extra가 기존을 덮어쓰게
    q.update({k: v for k, v in extra_params.items() if k})
    new_query = urlencode(q, doseq=True)
    return urlunparse((u.scheme, u.netloc, u.path, u.params, new_query, u.fragment))


def build_curl(method: str, url: str, headers: dict | None, body: dict | None) -> str:
    lines = [f"curl -X {method} \\"]
    lines.append(f"  '{url}' \\")
    if headers:
        for k, v in headers.items():
            lines.append(f"  -H '{k}: {v}' \\")
    if method.upper() == "POST" and body is not None:
        # json dump는 st.json과 다르게 "한 줄"이 curl에 더 자연스럽습니다
        import json
        lines.append(f"  -d '{json.dumps(body, ensure_ascii=False)}'")
    else:
        # 마지막 "\" 제거
        lines[-1] = lines[-1].rstrip(" \\")
    return "\n".join(lines)