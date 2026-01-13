import json
from typing import Dict, Any

def analyze_report_with_llm(report: dict, control_label: str, exp_label: str, llm_client) -> str:
    """
    결과 report를 읽고, 비전공자도 이해 가능한 한국어 자연어(마크다운) 리포트를 생성한다.
    반환값: markdown string
    """

    system_prompt = """
당신은 '검색 품질 평가 결과서'를 작성하는 데이터 분석가입니다.
독자가 아무것도 몰라도 이해할 수 있도록, 쉬운 한국어로 설명하세요.
반드시 JSON만 출력하세요(추가 텍스트 금지).
"""

    # summary 중심 + 일부 샘플만 전달 (길이/비용 방지)
    summary = report.get("summary", {}) or {}
    pairwise_samples = (report.get("pairwise_results") or [])[:5]
    ndcg_samples = (report.get("query_details") or [])[:5]

    user_prompt = f"""
    [입력 데이터]
    - Control 시스템명: {control_label}
    - Experimental 시스템명: {exp_label}
    
    - Summary:
    {json.dumps(summary, ensure_ascii=False, indent=2)}
    
    - Pairwise 결과 샘플(최대 5개):
    {json.dumps(pairwise_samples, ensure_ascii=False, indent=2)}
    
    - nDCG 상세 샘플(최대 5개):
    {json.dumps(ndcg_samples, ensure_ascii=False, indent=2)}
    
    [요구사항]
    아래 항목을 포함한 “한국어 마크다운 보고서”를 작성하세요.
    ※ 출력은 “마크다운 텍스트만” 작성하고, JSON/코드블록/추가 감싸기 없이 본문만 출력하세요.
    
    1) 한 줄 결론
    - 누가 우세인지 + 얼마나 확실한지(근거를 한 문장에 포함)
    
    2) 평가 방식 설명(처음 보는 사람도 이해 가능하게)
    - LLM-as-a-Judge가 뭔지
    - Pairwise와 nDCG가 각각 무엇을 평가하는지, 차이점
    
    3) 지표별 해석(수치는 summary의 값을 그대로 인용)
    - Pairwise(승/패/무): 무엇을 의미하며 이번 결과가 말하는 바
    - Bradley–Terry: score/prob를 어떻게 읽는지(직관 포함)
    - nDCG diff + 95% CI: diff의 의미, CI가 0 포함 여부 해석
    
    4) “이 결론을 믿어도 되는 조건 / 조심해야 하는 조건” (주의사항 3~5개)
    - 예: 표본 수, 쿼리 편향, 판단 기준 불일치, 노이즈/액세서리 비율 등
    
    5) 다음 액션 제안 3~5개
    - 예: Top/Bottom 쿼리 우선 분석, confidence 낮은 쿼리 재검토, 노이즈 패턴 제거 등
    
    [중요 규칙]
    - A/B/X/Y 같은 내부 표기는 절대 사용하지 말고, 반드시 “{control_label} / {exp_label}”만 사용하세요.
    - summary에 없는 수치는 절대 만들지 마세요. 필요하지만 없으면 “(해당 수치 제공되지 않음)”으로 표기하세요.
    - 단정 대신 근거 기반 표현 사용: “가능성이 큽니다 / 유의미하다고 보기 어렵습니다 / 경향이 있습니다”
    - 보고서 마지막에 “요약(3줄)” 섹션을 추가하세요.
    
    [출력 형식]
    - 오직 마크다운 본문 텍스트만 출력하세요.
    - 절대 JSON 출력 금지, 코드블록( ``` ) 사용 금지.
    - 만약 JSON(예: {{ "result": ... }} 형태)으로 출력하면 “오답 처리”되며 재시도를 하게 됩니다.
    - 첫 글자는 반드시 '#' 또는 일반 텍스트로 시작해야 하며, '{{' 로 시작하면 안 됩니다.
    """

    print("Analyzing report with LLM...")
    md = llm_client.generate_text(system_prompt, user_prompt)
    print("Analyzing report with LLM End.")
    return md