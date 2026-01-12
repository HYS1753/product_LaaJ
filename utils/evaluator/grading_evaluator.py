from typing import List, Any, Dict

from utils.evaluator.metrics import Metrics


class GradingEvaluator:
    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.GRADE_SYSTEM = """
        당신은 가전 제품 검색 관련도를 정확하게 평가하는 채점자입니다.
        반드시 유효한 JSON으로만 응답하세요. 추가 텍스트는 금지입니다.
        등급: 5(정확 일치) ~ 0(무관).
        제품 정보의 증거가 있을 때만 점수를 부여하세요. 불확실하면 낮게 평가하세요.
        """

        self.GRADE_USER_TMPL = """
        [채점 과제]
        주어진 사용자 쿼리와 검색 결과 리스트를 보고 각 상품이 쿼리에 얼마나 부합하는지 0~5점 관련도 등급을 부여하세요.
        평가는 구체적인 스펙·브랜드·모델·가격·출시일 등의 일치도를 기준으로 합니다.
        
        [쿼리]
        {query}
        
        [검색 결과 리스트] (1번이 최상위)
        {ranked_list}
        
        [출력 JSON 스키마]
        {{
          "grades": [g1, g2, ...],        // 각 상품에 대한 0~5 정수 점수
          "notes": ["항목1 이유", "항목2 이유", ...]  // 각 항목별 간단한 평가 근거 (30자 이내)
        }}
        
        (주의: 최종 JSON만 출력. 중간 계산/표/설명 출력 금지.)
        """

    def evaluate(self, query: str, results: List[Dict[str, Any]], k: int = 10) -> Dict[str, Any]:
        user_prompt = self.GRADE_USER_TMPL.format(
            query=query,
            ranked_list=results[:k],
        )
        out = self.llm_client.generate_json(self.GRADE_SYSTEM, user_prompt)

        grades = out.get("grades", [])
        notes = out.get("notes", [])

        # sanitize
        if not isinstance(grades, list):
            grades = []
        clean_grades: List[int] = []
        for g in grades[:k]:
            try:
                gi = int(g)
            except Exception:
                gi = 0
            clean_grades.append(max(0, min(5, gi)))

        if not isinstance(notes, list):
            notes = []
        clean_notes = [str(x)[:30] for x in notes[:k]]

        ndcg = Metrics.ndcg_at_k([float(x) for x in clean_grades], k)
        return {"grades": clean_grades, "notes": clean_notes, "ndcg": ndcg}