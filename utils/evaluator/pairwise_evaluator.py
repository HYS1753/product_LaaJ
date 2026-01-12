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
        다음 입력을 보고 두 결과 리스트(X/Y) 중 상위 {k}개가 쿼리를 더 잘 만족하는 쪽을 고르세요.
        반드시 내부적으로 추출→스코어링→검증을 거친 뒤 최종 JSON만 출력하세요. 설명 글을 장황하게 쓰지 마세요.

        [입력]
        [쿼리]
        {query}

        [리스트 X] (순위 중요)
        {list_x}

        [리스트 Y] (순위 중요)
        {list_y}

        [필드 매핑 가이드]
        • 제목: goodsNm
        • 브랜드: brndNm
        • 모델명: mdlNm
        • 가격: priceInfo.dscntSalePrc (없으면 salePrc)
        • 판매량: salesQty
        • 출시일: releaseDate
        • 스펙: goodsAttrs[].attrGrp/attrVal (검증 가능한 값만 사용)
        • 카테고리: dispCatFullNm

        [카테고리별 핵심 스펙]
        • 세탁기: 용량(kg), 드럼/통돌이, 브랜드
        • 냉장고: 용량(L), 도어 수, 브랜드
        • TV: 인치, 패널(OLED/QLED/LED), 해상도
        • 청소기: 유/무선, 브랜드, 모델
        • 노트북: CPU, RAM, GPU, 가격대
        (쿼리에서 카테고리가 명시되면 해당 스펙 가중 ↑. 불명확하면 제목/스펙에서 추정)

        [평가 절차(모델 내부 계산용 지침)]
        1. 쿼리 파싱: 브랜드/모델/인치/용량/가격대/폼팩터 등 핵심 제약조건을 구조화(숫자·단위 정규화).
        2. 항목 추출(각 리스트 상위 {k}개): 제목·브랜드·모델·가격·출시일·핵심 스펙을 추출. 검증 불가한 홍보문구는 무시.
        3. 스코어링(각 리스트별 총점 계산):
           • Relevance (0~5): 브랜드/모델·핵심 스펙 정확 일치도.
           • ConstraintFit (0~5): 가격/크기/용량 등 제약 충족률.
           • RankQuality (0~5): 상위에 좋은 매칭이 배치됐는지 (DCG/NDCG 개념, 대략 상위일수록 가중 ↑).
           • Freshness (0~3): 출시일 최근일수록 가중(연식 큰 차이 없으면 중립).
           • Trust (0~2): 판매량(log(salesQty+1))·명확한 스펙 기재 +, 모호/불일치/허위 –.
           • NoisePenalty (–0~3): 액세서리/케이스/필름 등 주제품이 아닌 항목 포함 시 감점(단, 쿼리가 액세서리를 원하면 감점 X).
           • 총점 = Relevance + ConstraintFit + RankQuality + Freshness + Trust – NoisePenalty
        4. 결정 규칙:
           • 두 총점 차가 1.0 이상이면 더 높은 쪽을 winner.
           • 0.5~0.99면 winner를 높은 쪽으로 하되 confidence 3.
           • 0.49 이하면 tie, confidence 2 이하.
           • 매우 미흡(둘 다 제약 미충족/노이즈 과다)이면 tie, confidence 1.
        5. 일관성 검증:
           • reason은 반드시 선택한 리스트명(X/Y)을 직접 언급하고, 그 구체 근거 1~2개만 50자 이내로 기술.
           • reason 안에 반대 리스트(Y/X)를 칭찬하거나 승자로 오인 표기 금지.
           • 모순 발견 시 이유만 재작성(승자/점수 유지).

        [추가 규칙]
        • 가격·인치·용량 등은 단위 정규화 후 비교.
        • 스펙이 제목/스펙 필드로 검증 가능할 때만 가점. 불명확·과장 문구는 가점 금지.
        • 동일 모델 중복은 노이즈로 간주(경미 –0.5).
        • “아이폰 케이스”처럼 액세서리 의도면 주기기(폰) 노출은 오히려 감점.

        [출력 JSON 스키마(최종 출력 전용)]
        {{
          "winner": "X" | "Y" | "tie",
          "confidence": 1 | 2 | 3 | 4 | 5,
          "reason": "50자 이내, 승자(X/Y) 명시 + 구체 근거 1~2개"
        }}

        (주의: 최종 JSON만 출력. 중간 계산/표/설명 출력 금지.)
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
            list_y=Y
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