import math
import random
import statistics
from typing import List, Tuple


class Metrics:
    @staticmethod
    def ndcg_at_k(gains: List[float], k: int) -> float:
        """
        [역할]
        - 랭킹 품질 지표인 nDCG@k(Normalized Discounted Cumulative Gain)를 계산한다.
        - "상위에 좋은(관련도 높은) 결과가 배치되었는가?"를 0~1 사이로 정규화해서 측정한다.

        [Input]
        - gains: List[float]
            각 순위(i)의 관련도 점수(grade)를 담은 리스트.
            예) gains = [5, 4, 0, 3, 1, ...]
            - gains[0] = 1등 결과의 관련도 점수
            - gains[1] = 2등 결과의 관련도 점수
            - ...
            * 점수 스케일은 0~5든 0~3이든 상관없지만, 일반적으로 "클수록 더 관련"이어야 한다.
        - k: int
            평가에 포함할 상위 개수.
            예) k=10이면 상위 10개 결과까지만 평가한다.

        [Output]
        - float (0.0 ~ 1.0)
            - 1.0에 가까울수록: 이상적으로 정렬된 랭킹에 가깝다.
            - 0.0에 가까울수록: 상위에 관련도 높은 문서가 잘 배치되지 않았다.
            - 모든 gain이 0이면 idcg가 0이라 정의상 0.0을 반환한다.

        [핵심 아이디어]
        1) DCG@k (Discounted Cumulative Gain)
           - 각 rank의 gain을 "로그 감쇠(log discount)"로 가중합한다.
           - 상위 랭크의 기여도가 더 크고, 아래로 갈수록 기여도가 감소한다.
           - 감쇠식: gain_i / log2(i+2)
             (i가 0부터 시작하므로 +2를 해서 log2(2)=1이 1등에 적용됨)

        2) IDCG@k (Ideal DCG)
           - 동일한 gains를 내림차순 정렬(=이론상 최적 랭킹)했을 때의 DCG@k.

        3) nDCG@k = DCG@k / IDCG@k
           - 쿼리마다 gain 분포가 달라도 0~1로 비교 가능하게 정규화한다.
        """
        if not gains or k <= 0:
            return 0.0

        # 실제 계산에 사용할 길이: gains가 k보다 짧을 수 있으니 min 처리
        kk = min(k, len(gains))

        # DCG@k: 현재 랭킹의 품질 점수
        # i=0(1등)일 때 log2(2)=1 → 감쇠 없음
        # i=1(2등)일 때 log2(3)로 나눠짐 → 감쇠
        dcg = sum((gains[i] / math.log2(i + 2)) for i in range(kk))

        # IDCG@k: 이상적인(최적) 랭킹의 DCG
        # gains를 내림차순 정렬한 후 동일한 DCG 공식을 적용한다.
        ideal = sorted(gains, reverse=True)
        idcg = sum((ideal[i] / math.log2(i + 2)) for i in range(kk))

        # idcg가 0이면(즉, 모든 gain이 0이면) 정규화가 불가능하므로 0 반환
        return dcg / idcg if idcg > 0 else 0.0

    @staticmethod
    def bootstrap_ci(
        samples: List[float],
        iters: int = 2000,
        alpha: float = 0.05
    ) -> Tuple[float, float]:
        """
        [역할]
        - Bootstrap(재표본추출)로 "표본 평균(mean)의 신뢰구간"을 근사한다.
        - 즉, samples가 있을 때 평균이 어느 범위에 있을지 (예: 95% CI)를 계산.

        [Input]
        - samples: List[float]
            관측된 값들의 리스트.
            예) 각 쿼리별 (nDCG_A - nDCG_B) 차이값들:
                samples = [0.12, -0.03, 0.05, ...]
        - iters: int (default=2000)
            부트스트랩 반복 횟수.
            - 클수록 더 안정적이지만 계산량 증가.
        - alpha: float (default=0.05)
            유의수준.
            - alpha=0.05 → 95% 신뢰구간(= 2.5% ~ 97.5% 분위수)
            - alpha=0.10 → 90% 신뢰구간(= 5% ~ 95%)

        [Output]
        - (float, float) = (lower_bound, upper_bound)
            평균에 대한 신뢰구간.
            예) (0.01, 0.08) 이면,
                "평균 차이가 대략 0.01~0.08 범위일 가능성이 높다"는 해석.

        [핵심 아이디어]
        - samples를 '모집단'처럼 보고, 같은 길이(n)의 표본을 "복원추출"로 여러 번 뽑는다.
        - 각 재표본(resample)마다 평균을 계산하여 boot 리스트에 저장한다.
        - boot의 분위수를 신뢰구간으로 사용한다.
        """
        if not samples:
            return (0.0, 0.0)

        n = len(samples)
        boot: List[float] = []

        # iters번 반복:
        # 1) samples에서 길이 n 만큼 "복원추출"로 resample 생성
        # 2) resample 평균을 boot에 저장
        for _ in range(iters):
            resample = [samples[random.randrange(n)] for _ in range(n)]
            boot.append(statistics.mean(resample))

        # 분위수 계산을 위해 정렬
        boot.sort()

        # 하한/상한 인덱스:
        # alpha=0.05이면 lo=0.025, hi=0.975 분위수
        lo = int((alpha / 2) * iters)
        hi = int((1 - alpha / 2) * iters)

        # 안전장치: hi가 iters-1을 넘지 않게 보정
        hi = min(hi, iters - 1)

        return (boot[lo], boot[hi])

    @staticmethod
    def bradley_terry(
        win_pairs: List[str],
        iters: int = 200,
        lr: float = 0.1
    ) -> Tuple[float, float]:
        """
        [역할]
        - Pairwise 승패 결과(‘A’/‘B’/‘tie’)로부터
          Bradley-Terry 모델을 사용해 A의 상대 강도(strength)와
          A가 B를 이길 확률을 추정한다.

        [Bradley-Terry 직관]
        - 각 시스템(A, B)은 '강도' 파라미터 s_A, s_B를 가진다.
        - A가 B를 이길 확률:
              P(A wins) = exp(s_A) / (exp(s_A) + exp(s_B))
        - 여기서는 s_B = 0으로 고정하고 s_A만 학습해서
          "A가 B보다 얼마나 강한가"를 s_A 하나로 표현한다.

        [Input]
        - win_pairs: List[str]
            각 쿼리에 대한 pairwise 판정 결과 리스트.
            원소는 'A', 'B', 'tie' 중 하나.
            예) ['A', 'A', 'tie', 'B', ...]
            의미:
              - 'A'  : A가 이김
              - 'B'  : B가 이김
              - 'tie': 무승부 (동급)

        - iters: int (default=200)
            경사상승(gradient ascent) 업데이트 반복 횟수.
            - 클수록 수렴에 유리하지만 시간이 증가.

        - lr: float (default=0.1)
            학습률(업데이트 스텝 크기).
            - 너무 크면 발산 가능, 너무 작으면 수렴이 느림.

        [Output]
        - (float, float) = (score_diff_for_A, prob_A_beats_B)
            1) score_diff_for_A (= sA):
               - 0보다 크면 A가 더 강한 경향
               - 0보다 작으면 B가 더 강한 경향
               - 절댓값이 클수록 차이가 크다.
            2) prob_A_beats_B:
               - 로지스틱 변환으로 얻는 A의 승률 추정치 (0~1)
               - 예) 0.63이면 "A가 B를 이길 확률이 약 63%"라는 의미

        [계산 절차(현재 구현의 핵심)]
        - sB=0 고정, sA만 업데이트.
        - 각 관측 w에 대해 현재 pA = P(A wins) 계산.
        - 관측값을 수치화:
            A 승 = 1.0
            B 승 = 0.0
            tie  = 0.5
          라고 보고 (관측 - 예측)을 누적한 형태로 grad를 만든다.
        - sA <- sA + lr * grad / N
          (N으로 나눠 스케일을 안정화)

        [주의]
        - 이 구현은 간단한 2-시스템 버전이며, 정교한 BT(다수 시스템) 확장과는 다르다.
        - tie 처리는 0.5로 근사한 휴리스틱이다.
        """
        if not win_pairs:
            return (0.0, 0.5)

        sA = 0.0  # A의 강도 파라미터 (B는 0으로 고정)

        for _ in range(iters):
            grad = 0.0

            for w in win_pairs:
                # 현재 파라미터에서 A가 이길 확률 pA 계산
                # pA = exp(sA) / (exp(sA) + exp(0))
                pA = math.exp(sA) / (math.exp(sA) + math.exp(0.0))

                # 관측값(target) - 예측값(pA) 형태로 gradient를 누적
                # A 승: target=1
                # B 승: target=0
                # tie : target=0.5
                if w == 'A':
                    grad += (1 - pA)
                elif w == 'B':
                    grad += (0 - pA)
                else:
                    grad += (0.5 - pA)

            # 평균 gradient로 업데이트 (스케일 안정화)
            sA += lr * grad / max(1, len(win_pairs))

        # 최종 sA를 확률로 변환 (시그모이드/로지스틱)
        # prob = 1 / (1 + exp(-sA))
        prob_A = 1 / (1 + math.exp(-sA))

        return (sA, prob_A)