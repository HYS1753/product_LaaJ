import os
import json
import time
from typing import Any, Dict, Optional
from google import genai
from google.genai import types

class GeminiClient:
    def __init__(
            self,
            api_key: Optional[str] = None,
            model_name: Optional[str] = None,
            temperature: Optional[float] = None,
            max_retries: Optional[int] = None
    ):
        # 1. 환경 변수 또는 사용자 입력값으로 설정 (우선순위: 사용자 입력 > .env)
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name or os.getenv("GEMINI_API_MODEL", "gemini-2.5-flash")

        # 환경 변수에서 가져올 때 숫자로 변환 (기본값 설정)
        env_temp = os.getenv("GEMINI_API_TEMPERATURE", "0.0")
        self.temperature = float(temperature if temperature is not None else env_temp)

        env_retries = os.getenv("GEMINI_API_MAX_RETRIES", "3")
        self.max_retries = int(max_retries if max_retries is not None else env_retries)

        # 2. 클라이언트 초기화
        if not self.api_key:
            raise ValueError("API Key가 설정되지 않았습니다. .env 파일을 확인하거나 api_key를 전달하세요.")

        self.client = genai.Client(api_key=self.api_key)

    def generate_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        last_err: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                # 새로운 SDK의 generate_content 방식
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,  # 시스템 프롬프트 분리
                        temperature=self.temperature,
                        response_mime_type="application/json",  # JSON 응답 강제
                    ),
                )

                # 응답 텍스트 파싱
                return json.loads(response.text)

            except Exception as e:
                last_err = e
                print(f"오류 발생 (시도 {attempt + 1}/{self.max_retries}): {e}")
                time.sleep(1.5 * (attempt + 1))  # 지수 백오프

        print(f"최종 실패: {last_err}")
        return {}

    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        last_err = None
        for attempt in range(self.max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=self.temperature,
                        # ✅ JSON 강제하지 않음
                    ),
                )
                return (response.text or "").strip()
            except Exception as e:
                last_err = e
                print(f"오류 발생 (시도 {attempt + 1}/{self.max_retries}): {e}")
                time.sleep(1.5 * (attempt + 1))
        print(f"최종 실패: {last_err}")
        return ""