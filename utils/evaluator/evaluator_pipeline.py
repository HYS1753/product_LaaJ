import statistics
from typing import Optional, Callable, List, Dict, Any, Tuple
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from config.llm_client_factory import LLMProvider, LLMClientFactory
from utils.evaluator.grading_evaluator import GradingEvaluator
from utils.evaluator.metrics import Metrics
from utils.evaluator.pairwise_evaluator import PairwiseEvaluator
from utils.evaluator.result_json_parser import ResultsJsonParser


class EvaluationPipeline:
    """
    병렬 평가 파이프라인 (쿼리 단위 병렬)

    핵심 아이디어:
      - 쿼리 1개를 처리하는 데 LLM 호출이 보통 3번 발생:
          1) pairwise: A vs B 승자 판단
          2) grading A: A 리스트 관련도 채점 + nDCG
          3) grading B: B 리스트 관련도 채점 + nDCG
      - 이를 "쿼리 단위"로 병렬 처리하면 전체 시간이 크게 단축됨.
    """
    def __init__(
            self,
            provider: LLMProvider,
            topk: int = 20,
            progress_callback: Optional[Callable[[float], None]] = None,
    ):
        # 원활한 병렬 처리를 위한 llm 클라이언트 worker 별로 생성
        self.llm_client_factory = LLMClientFactory(provider=provider)
        self.topk = topk
        self.progress_callback = progress_callback

    def run_parallel(
        self,
        payload: Dict[str, Any],
        max_workers: int = 8,
    ) -> Dict[str, Any]:
        """
        [병렬 실행 flow 개요]

        (1) 입력(queries) 각각을 "작업(task)"으로 만들어 ThreadPoolExecutor에 제출
        (2) 각 task(worker)는:
            - qid로 A/B 결과를 꺼내고,
            - (pairwise 1회 + grading 2회) LLM 호출을 수행하고,
            - (pairwise_row, detail_row, ndcg_diff)를 반환
        (3) 메인 스레드는 as_completed로 완료되는 task부터 결과를 수집/누적
        (4) 모든 task가 끝나면, 누적된 결과를 Metrics로 집계하여 summary 생성

        반환 구조:
          {
            "summary": {...},
            "pairwise_results": [...],
            "query_details": [...],
            "config": {...}
          }
        """

        parser = ResultsJsonParser(default_topk=self.topk)
        queries, results_A, results_B = parser.parse(payload)
        total = len(queries)

        # 여기서 k=0인 쿼리(한쪽 결과가 비어서 min=0) 제거하여 효율성 증대
        queries = [q for q in queries if q.get("topk", 0) > 0]

        # ---------------------------------------
        # [A] 병렬 수행 결과를 모아둘 리스트들
        # ---------------------------------------
        pairwise_results: List[Dict[str, Any]] = []  # 쿼리별 pairwise 결과 누적
        query_details: List[Dict[str, Any]] = []    # 쿼리별 grading 상세 누적
        ndcg_samples: List[float] = []              # 쿼리별 ndcg_A - ndcg_B 샘플 누적

        # 진행률 계산용(완료된 task 수)
        done = 0

        # ---------------------------------------
        # [B] worker: "쿼리 1개"를 처리하는 단위 작업
        # ---------------------------------------
        def worker(q_item: Dict[str, Any]) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], float]]:
            """
            [worker flow]
            1) qid/query/k 추출
            2) results_A[qid], results_B[qid] 가져오기
            3) 비어있으면 평가 불가 → None 반환
            4) (중요) 이 worker 전용 LLM client 생성 (스레드 안전성 확보)
            5) PairwiseEvaluator로 A vs B 판정 (LLM 호출 1회)
            6) GradingEvaluator로 A 채점 (LLM 호출 1회)
            7) GradingEvaluator로 B 채점 (LLM 호출 1회)
            8) ndcg_diff 계산 후, 결과(row 2개 + diff) 반환
            """

            # 1) qid/query/k 준비
            qid = q_item["qid"]
            query = q_item.get("query") or q_item.get("question") or q_item.get("q") or ""
            k = min(int(q_item.get("topk", self.topk)), self.topk)

            # 2) A/B 결과 취득
            A = results_A.get(qid, [])
            B = results_B.get(qid, [])

            # 3) 한쪽이라도 비어있으면 skip
            if not A or not B:
                return None

            # 4) worker(스레드) 전용 LLM client 생성
            #    - 이게 llm_client_factory의 핵심 역할
            local_client = self.llm_client_factory.create()

            # 5) evaluator 인스턴스도 worker 내부에서 생성해서
            #    client 공유/상태 공유 문제를 회피
            pairwise = PairwiseEvaluator(llm_client=local_client)
            grading = GradingEvaluator(llm_client=local_client)

            # 6) pairwise LLM 호출
            pw = pairwise.evaluate(query, A, B, k)

            # 7) grading LLM 호출 (A/B 각각)
            gA = grading.evaluate(query, A, k)
            gB = grading.evaluate(query, B, k)

            # 8) ndcg 차이 계산
            ndcg_diff = gA["ndcg"] - gB["ndcg"]

            # 반환용 row 구성
            pairwise_row = {
                "qid": qid,
                "query": query,
                "winner": pw["winner"],
                "confidence": pw["confidence"],
                "reason": pw["reason"],
            }

            detail_row = {
                "qid": qid,
                "query": query,
                "ndcg_control": gA["ndcg"],
                "ndcg_experimental": gB["ndcg"],
                "ndcg_diff": ndcg_diff,
                "grades_control": gA["grades"],
                "grades_experimental": gB["grades"],
                "notes_control": gA["notes"],
                "notes_experimental": gB["notes"],
            }

            return pairwise_row, detail_row, ndcg_diff

        # ---------------------------------------
        # [C] ThreadPoolExecutor로 모든 쿼리를 병렬 제출
        # ---------------------------------------
        # - max_workers 만큼 동시에 worker가 실행된다.
        # - LLM 호출은 네트워크 I/O라서 threads로도 속도 개선이 큰 편.
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(worker, q) for q in queries]

            # ---------------------------------------
            # [D] 완료되는 순서대로 결과 수집
            # ---------------------------------------
            for fut in as_completed(futures):
                res = fut.result()

                # worker가 None을 반환하면(평가 불가) 그냥 통과
                if res is not None:
                    pw_row, detail_row, diff = res
                    pairwise_results.append(pw_row)
                    query_details.append(detail_row)
                    ndcg_samples.append(diff)

                # 진행률 업데이트: "완료된 task / 전체 task"
                done += 1
                if self.progress_callback:
                    self.progress_callback(done / max(1, total))

        # ---------------------------------------
        # [E] 모든 쿼리 병렬 처리 종료 후, 통계 집계
        # ---------------------------------------
        return self._finalize(total, pairwise_results, query_details, ndcg_samples)

    def _finalize(
        self,
        total: int,
        pairwise_results: List[Dict[str, Any]],
        query_details: List[Dict[str, Any]],
        ndcg_samples: List[float],
    ) -> Dict[str, Any]:
        """
        [집계 flow]
        1) pairwise winner 카운팅 → winrate_A 계산
        2) Bradley-Terry로 상대강도/승률 추정
        3) ndcg_diff 샘플 평균 및 bootstrap CI 계산
        4) summary + 상세 결과 반환
        """

        wins = Counter(p["winner"] for p in pairwise_results)
        wA, wB, wT = wins.get("A", 0), wins.get("B", 0), wins.get("tie", 0)

        # 무승부를 제외한 유효 승부 건수 기준 A 승률
        n_eff = wA + wB
        winrate_A = (wA / n_eff) if n_eff > 0 else 0.5

        # Bradley-Terry (A vs B 상대강도)
        bt_score, bt_prob = Metrics.bradley_terry([p["winner"] for p in pairwise_results])

        # nDCG 차이 통계
        mean_ndcg_diff = statistics.mean(ndcg_samples) if ndcg_samples else 0.0
        ci_lo, ci_hi = Metrics.bootstrap_ci(ndcg_samples) if ndcg_samples else (0.0, 0.0)

        # 결과 정렬
        pairwise_results_sorted = sorted(
            pairwise_results,
            key=lambda d: int(str(d.get("qid", "")).lstrip("q") or 10 ** 9)
        )

        query_details_sorted = sorted(
            query_details,
            key=lambda d: int(str(d.get("qid", "")).lstrip("q") or 10 ** 9)
        )

        return {
            "summary": {
                "total_queries": total,
                "evaluated_queries": len(pairwise_results),
                "pairwise": {
                    "win_control": wA,
                    "win_experimental": wB,
                    "tie": wT,
                    "winrate_control": round(winrate_A, 4),
                    "bradley_terry_score": round(bt_score, 4),
                    "bradley_terry_prob_control": round(bt_prob, 4),
                },
                "ndcg": {
                    "mean_diff_control_minus_experimental": round(mean_ndcg_diff, 4),
                    "ci_95_lower": round(ci_lo, 4),
                    "ci_95_upper": round(ci_hi, 4),
                },
            },
            "pairwise_results": pairwise_results_sorted,
            "query_details": query_details_sorted,
            "config": {"topk": self.topk},
        }