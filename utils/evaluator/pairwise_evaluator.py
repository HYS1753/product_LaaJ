import random

from typing import List, Dict, Any

class PairwiseEvaluator:
    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.PAIRWISE_SYSTEM = """
        당신은 가전 제품 검색 품질을 평가하는 엄격한 심사위원입니다.
        반드시 유효한 JSON 형식으로만 응답하세요. 간결하되 결정적으로 판단하세요.
        허위 정보나 무관한 항목은 감점하세요.
        두 리스트가 동등한 품질이면 tie를 반환하세요.
        """

        self.PAIRWISE_USER_TMPL = """
        [평가 과제]
        다음 입력을 보고 두 검색 시스템의 결과 리스트 중
        **상위 {k}개 기준으로 쿼리를 더 잘 만족하는 시스템**을 선택하세요.
        
        반드시 내부적으로
        쿼리 해석 → 증거 추출 → 리스트별 품질 비교 → 검증
        을 거친 뒤 **최종 JSON만 출력**하세요.
        불필요한 설명은 금지합니다.
        
        ---
        
        [쿼리]
        {query}
        
        ---
        
        [시스템 매핑]
        - 시스템 X: **{x_label}**
        - 시스템 Y: **{y_label}**
        
        ⚠️ 출력 규칙
        - winner 필드는 반드시 `"X" | "Y" | "tie"` 중 하나
        - reason에는 **X/Y라는 문자를 절대 사용하지 말고**
          반드시 **{x_label} 또는 {y_label} 시스템명만 사용**하세요
        
        ---
        
        [시스템 X 결과 리스트] (순위 중요)
        {list_x}
        
        [시스템 Y 결과 리스트] (순위 중요)
        {list_y}
        
        ---
        
        [범용 증거 추출 가이드 (필드 비고정)]
        각 결과 아이템은 시스템마다 구조와 필드명이 다를 수 있습니다.
        따라서 **아이템 내부 어디에 있든**, 다음 정보를 찾아 근거로 사용하세요:
        
        - 제목 / 이름 / 상품명 / 문서명
        - 브랜드 / 제조사 / 공급자
        - 모델명 / SKU / 품번
        - 가격 또는 가격대 정보
        - 카테고리 / 분류 / 태그
        - 스펙 / 속성 / 옵션 (숫자·단위 포함)
        - 출시일 / 연식 / 최신성
        - 판매량 / 리뷰수 / 인기 지표
        
        ✅ 위 정보가 어떤 키에 있든 “검증 가능한 증거”로 인정  
        ❌ 근거 없는 홍보 문구(최신형, 인기, 추천 등)는 증거 불가
        
        ---
        
        [쿼리 의도 해석]
        1. 쿼리에서 가능한 제약조건을 추출하세요:
           - 제품/카테고리
           - 브랜드/모델
           - 핵심 스펙(용량, 인치, 성능 등)
           - 가격대 / 폼팩터 / 사용 목적
        
        2. 명시된 조건일수록 가중치를 높이세요.
        3. 추정이 필요한 경우, 불확실하면 감점하세요.
        
        ---
        
        [카테고리별 핵심 스펙 힌트]
        - 냉장고: 용량(L), 도어 수, 타입
        - 세탁기: 용량(kg), 드럼/통돌이
        - TV/디스플레이: 인치, 패널, 해상도
        - 청소기: 유/무선, 형태
        - 노트북: CPU, RAM, GPU, 가격대
        
        (쿼리에 카테고리가 명시되면 해당 스펙 중요도 ↑)
        
        ---
        
        [리스트 품질 비교 기준]
        각 시스템별로 상위 {k}개를 기준으로 종합 판단하세요.
        
        - Relevance (0~5): 쿼리 핵심 조건과의 일치도
        - ConstraintFit (0~5): 가격/스펙/형태 등 제약 충족률
        - RankQuality (0~5): 좋은 매칭이 상위에 배치되었는지
        - Freshness (0~3): 연식/최신성
        - Trust (0~2): 명확한 스펙, 신뢰 가능한 정보
        - NoisePenalty (–0~3): 무관/액세서리/중복/노이즈
        
        총점 = 위 요소들의 종합 판단 (정확한 수치 계산은 내부 판단용)
        
        ---
        
        [결정 규칙]
        - 총점 차 ≥ 1.0 → 더 높은 시스템이 winner
        - 0.5 ~ 0.99 → 더 높은 쪽 winner, confidence = 3
        - < 0.5 → tie
        - 양쪽 모두 미흡/노이즈 과다 → tie, confidence ≤ 2
        
        ---
        
        [reason 작성 규칙 (중요)]
        - 반드시 승자 시스템명(**{x_label} 또는 {y_label}**)을 직접 언급
        - **왜 더 나았는지 핵심 근거 1~2개만**
        - 50자 이내
        - 패자 시스템을 칭찬하거나 혼동되는 표현 금지
        
        예시:
        - "{x_label}는 상위에 쿼리 일치 모델이 집중 배치됨"
        - "{y_label}는 노이즈 항목 비율이 높음"
        
        ---
        
        [출력 JSON 스키마]
        {{
          "winner": "X" | "Y" | "tie",
          "confidence": 1 | 2 | 3 | 4 | 5,
          "reason": "50자 이내, 승자 시스템명 명시 + 구체 근거"
        }}
        
        (주의: 최종 JSON만 출력. 중간 계산/설명 출력 금지.)
        """

    def evaluate(self, query: str, results_A: List[Dict[str, Any]], results_B: List[Dict[str, Any]], k: int = 10) -> Dict[str, Any]:
        # 위치 편향 완화용 랜덤 스왑
        if random.random() < 0.5:
            X, Y = results_A[:k], results_B[:k]
            XY_map = {"X": "A", "Y": "B"}
        else:
            X, Y = results_B[:k], results_A[:k]
            XY_map = {"X": "B", "Y": "A"}

        user_prompt = self.PAIRWISE_USER_TMPL.format(
            k=k,
            query=query,
            list_x=X,
            list_y=Y,
            x_label=XY_map["X"],
            y_label=XY_map["Y"],
        )

        out = self.llm_client.generate_json(self.PAIRWISE_SYSTEM, user_prompt)

        winner_xy = out.get("winner", "tie")
        winner = XY_map.get(winner_xy, "tie") if winner_xy in ("X", "Y") else "tie"

        conf = out.get("confidence", 3)
        try:
            conf = int(conf)
        except Exception:
            conf = 3
        conf = max(1, min(5, conf))

        reason = out.get("reason", "")
        return {"winner": winner, "confidence": conf, "reason": reason}