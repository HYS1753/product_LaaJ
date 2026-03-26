from typing import List, Any, Dict

from utils.evaluator.metrics import Metrics


class GradingEvaluator:
    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.GRADE_SYSTEM = """
        당신은 가전 제품 검색 결과의 **관련도(relevance)**를 정밀하게 채점하는 평가자입니다.
        반드시 유효한 JSON으로만 응답하세요. 추가 텍스트는 절대 출력하지 마세요.
        
        당신의 목표는:
        - “이 상품이 사용자가 실제로 찾으려던 제품인가?”를 판단하는 것입니다.
        - 검색 랭킹 평가(nDCG)에 사용되므로 **상위 노출 상품일수록 더 엄격하게 평가**하세요.
        
        점수는 반드시 **상품 정보에 근거**해야 합니다.
        검증 불가능하거나 추정/광고성 문구만 있는 경우 낮은 점수를 부여하세요.
        
        점수 범위: 0(무관) ~ 5(정확 일치)
        """

        self.GRADE_USER_TMPL = """
        [채점 과제]
        아래의 **사용자 쿼리**와 **검색 결과 리스트(순위 중요)**를 보고,
        각 결과(상품/문서/아이템)가 쿼리를 얼마나 잘 만족하는지 **0~5점 관련도 점수**를 부여하세요.
        
        이 점수는 nDCG 계산에 사용되므로,
        - 상위에 노출될수록 더 엄격하게 평가하세요.
        - “그럴듯해 보임”이 아니라 **아이템 내부의 증거(텍스트/숫자/속성)**로만 판단하세요.
        - 증거가 부족하거나 불확실하면 점수를 낮게 주세요.
        
        ---
        
        [쿼리]
        {query}
        
        ---
        
        [검색 결과 리스트] (1번이 최상위, 순위 중요)
        {ranked_list}
        
        ---
        
        [증거 기반 평가 규칙 (필드명 범용)]
        각 아이템은 회사/시스템마다 필드명이 다를 수 있습니다.
        따라서 **아이템 내부에서 다음 정보가 어디에 있든 찾아서** 평가하세요:
        
        - 제목/상품명/문서명 (예: title, name, goodsNm, productName 등)
        - 브랜드/제조사 (예: brand, maker, brndNm 등)
        - 모델명/품번 (예: model, sku, mdlNm 등)
        - 가격/가격대 (예: price, salePrice, discountedPrice, priceInfo 등)
        - 카테고리/분류 (예: category, dispCatFullNm, taxonomy 등)
        - 스펙/속성 목록 (예: attributes, specs, options, goodsAttrs 등)
        - 출시일/연식 (예: releaseDate, launchedAt 등)
        - 판매량/인기지표 (예: salesQty, soldCount, ratingCount 등)
        - 프로모션/혜택 정보 (예: salePrice, discountedPrice, coupon, couponPrice, cardDiscount, immediateDiscount, benefit, promotionText, eventBadge 등)
        
        ✅ 위 정보가 “어떤 키에 있든” 근거로 사용할 수 있습니다.  
        ❌ 반대로, 아이템 안에 **근거가 전혀 없으면** 높은 점수를 주지 마세요.
        
        ✅ 단, 프로모션은 아이템 내부의 수치/조건/혜택 문구로 검증 가능할 때만 근거로 사용하세요.
        ❌ "특가", "혜택가", "할인중", "가성비"처럼 구체 금액/조건 없는 마케팅 문구는 근거로 인정하지 마세요.
        
        또한 다음과 같은 **검증 불가능한 마케팅 문구**는 근거로 인정하지 마세요:
        - “최신형”, “고성능”, “인기상품”, “가성비”, “추천” 등
        
        ---
        
        [쿼리 의도 해석 지침]
        1) 쿼리에서 가능한 제약조건을 추출하세요:
           - 제품/카테고리(예: 냉장고/TV/세탁기/노트북 등)
           - 브랜드/모델명
           - 핵심 스펙(용량, 인치, 패널, CPU, RAM 등)
           - 가격대/크기/용량 조건
           - 폼팩터(드럼/통돌이, 스탠드형 등)
        
        2) 쿼리에 명시된 제약조건은 최우선으로 평가하세요.
        3) 카테고리가 불명확하면, 제목/스펙에서 추정하되 불확실하면 감점하세요.
        
        ---
        
        [카테고리별 핵심 스펙 가이드]
        - 냉장고: 용량(L), 도어 수, 형태(일반/김치/양문형 등)
        - 세탁기: 용량(kg), 드럼/통돌이
        - TV/디스플레이: 인치, 패널(OLED/QLED/LED), 해상도
        - 청소기: 유/무선, 형태(스틱/로봇 등)
        - 노트북: CPU, RAM, GPU, 무게/화면크기, 가격대
        
        (쿼리에 카테고리가 명시되면 해당 스펙의 중요도를 크게 높이세요.)
        
        ---
        
        [프로모션 가중 규칙]
        - 프로모션 정보는 **관련도 보조 신호**입니다.
        - 카테고리/브랜드/모델/핵심 스펙/가격대가 비슷하게 맞는 후보들 사이에서는,
          **실구매 혜택이 더 큰 상품**(명시적 할인, 쿠폰 적용가, 카드 할인, 사은품 등)에 더 높은 점수를 줄 수 있습니다.
        - 단, 프로모션이 있어도 쿼리 핵심 조건이 맞지 않으면 높은 점수를 주지 마세요.
        - 프로모션 가점은 최대 1점 범위의 미세 조정으로 사용하세요.
          예: 기본 4점 후보 중 혜택이 명확히 더 좋으면 5점, 근거 없는 홍보성 문구면 가점 없음.
        
        ---
        
        [관련도 점수 기준 (0~5)]
        5점 (정확 일치)
        - 쿼리의 핵심 조건(카테고리/브랜드/모델/핵심 스펙/가격대)이 **근거로 확인되며** 거의 완벽히 일치
        
        4점 (근접 일치)
        - 카테고리와 주요 조건 대부분이 일치
        - 일부 경미한 차이(용량/가격 소폭 차이, 유사 라인업 등)
        
        3점 (부분 일치)
        - 같은 카테고리이지만 조건 일부만 충족
        - 대안으로 고려 가능하나 제약조건 불일치가 존재
        
        2점 (약한 관련)
        - 카테고리는 같거나 유사하지만 브랜드/스펙/가격대가 전반적으로 불일치
        
        1점 (간접 관련)
        - 유사 제품군이나 사용 의도가 다름
        - 예: TV 쿼리에 모니터, 냉장고 쿼리에 김치냉장고(일반 냉장고 의도인 경우)
        
        0점 (무관)
        - 전혀 다른 카테고리이거나, 액세서리/소모품/서비스 등
        - 단, 쿼리가 액세서리를 명시하면 그 경우는 예외
        
        ---
        
        [notes 작성 규칙]
        - notes는 각 아이템별 30자 이내
        - “어떤 근거”로 점수를 줬는지 핵심만 쓰세요
          예: “용량/모델 불일치”, “브랜드 일치+인치 일치”, “카테고리 무관”
        
        ---
        
        [출력 JSON 스키마]
        {{
          "grades": [g1, g2, ...],        // 각 아이템에 대한 0~5 정수 점수
          "notes": ["item1 근거", "item2 근거", ...]
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