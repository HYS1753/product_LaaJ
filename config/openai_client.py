import os
import json
import time
from typing import Any, Dict, Optional
from openai import OpenAI

class OpenAIClient:
    def __init__(
            self,
            api_key: Optional[str] = None,
            model_name: Optional[str] = None,
            temperature: Optional[float] = None,
            max_retries: Optional[int] = None
    ):
        # 1. 환경 변수 또는 사용자 입력값으로 설정 (우선순위: 사용자 입력 > .env)
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model_name = model_name or os.getenv("OPENAI_API_MODEL", "gpt-4o")

        env_temp = os.getenv("OPENAI_API_TEMPERATURE", "0.0")
        self.temperature = float(temperature if temperature is not None else env_temp)

        env_retries = os.getenv("OPENAI_API_MAX_RETRIES", "3")
        self.max_retries = int(max_retries if max_retries is not None else env_retries)

        # 2. 클라이언트 초기화
        if not self.api_key:
            raise ValueError("OpenAI API Key가 설정되지 않았습니다.")

        self.client = OpenAI(api_key=self.api_key)

    def generate_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        last_err: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                # OpenAI Chat Completion 호출
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=self.temperature,
                    # JSON 모드 활성화 (반드시 프롬프트에 'json'이라는 단어가 포함되어야 안정적입니다)
                    response_format={"type": "json_object"}
                )

                # 응답 텍스트 파싱
                content = response.choices[0].message.content
                return json.loads(content) if content else {}

            except Exception as e:
                last_err = e
                print(f"OpenAI 오류 발생 (시도 {attempt + 1}/{self.max_retries}): {e}")
                time.sleep(1.5 * (attempt + 1))

        print(f"OpenAI 최종 실패: {last_err}")
        return {}


