from typing import Dict, Tuple, Any, List

class ResultsJsonParser:
    """
    너가 준 JSON 포맷을 pipeline 입력(queries, results_A, results_B)으로 변환.
    - keywords/control_config/experimental_config는 무시
    - results[]만 사용
    - topk는 min(len(A), len(B), default_topk)로 결정
    """

    def __init__(self, default_topk: int = 20):
        self.default_topk = default_topk

    def parse(self, payload: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]], Dict[str, List[Dict[str, Any]]]]:
        rows = payload.get("results") or []

        queries: List[Dict[str, Any]] = []
        results_A: Dict[str, List[Dict[str, Any]]] = {}
        results_B: Dict[str, List[Dict[str, Any]]] = {}

        for idx, row in enumerate(rows):
            query = row.get("keyword") or ""
            qid = f"q{idx+1}"

            control_list = ((row.get("control") or {}).get("result")) or []
            exp_list = ((row.get("experimental") or {}).get("result")) or []

            # judge-friendly 포맷으로 변환
            A = [x for x in control_list]
            B = [x for x in exp_list]

            # ✅ 공정 비교 top-k 정의: 둘 중 더 짧은 길이에 맞춤
            effective_k = min(self.default_topk, len(A), len(B))

            queries.append({
                "qid": qid,
                "query": query,
                "topk": effective_k,
            })
            results_A[qid] = A
            results_B[qid] = B

        return queries, results_A, results_B