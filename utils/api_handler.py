import requests
import json
from typing import Dict, Any, Optional


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