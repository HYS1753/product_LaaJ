import json
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode

import matplotlib.pyplot as plt

from config.gemini_client import GeminiClient
from utils.analyzer.analyze_report_with_llm import analyze_report_with_llm
from utils.markdown_wrapper import unwrap_markdown


# =========================================================
# Paths
# =========================================================
def _project_root() -> Path:
    return Path.cwd()


def _results_dir() -> Path:
    d = _project_root() / "test_results"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fmt_dt(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "-"


def _read_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _json_pretty(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


# =========================================================
# State
# =========================================================
def _init_state():
    # mode: "list" (목록) | "report" (선택 결과 리포트 단독)
    st.session_state.setdefault("results_mode", "list")
    st.session_state.setdefault("results_selected_path", None)
    st.session_state.setdefault("results_loaded_obj", None)
    st.session_state.setdefault("results_active_tab", "1) Overview")


def _reset_state_to_list():
    st.session_state.results_mode = "list"
    st.session_state.results_selected_path = None
    st.session_state.results_loaded_obj = None
    st.session_state.results_active_tab = "1) Overview"


# =========================================================
# Helpers: schema normalize (Control/Experimental naming)
# =========================================================
def _infer_labels(summary_pairwise: dict) -> tuple[str, str]:
    """
    summary.pairwise 키가 win_control/win_experimental 형태면 그걸 쓰고,
    아니면 fallback으로 Control/Experimental 반환.
    """
    keys = set((summary_pairwise or {}).keys())
    if "win_control" in keys or "win_experimental" in keys:
        return "Control", "Experimental"
    # 기존 파이프라인이 A/B로 저장한 경우 등 확장 여지
    return "Control", "Experimental"


def _winner_to_label(winner: str, control_label="Control", exp_label="Experimental") -> str:
    # 너가 말한 규칙: A=control, B=experimental
    if winner == "A":
        return control_label
    if winner == "B":
        return exp_label
    return "Tie"


def _summary_get(report: dict) -> dict:
    return report.get("summary") or {}


# =========================================================
# Charts
# =========================================================
def _plot_pairwise_pie(w_control: int, w_exp: int, w_tie: int, control_label: str, exp_label: str):
    labels = [control_label, exp_label, "Tie"]
    values = [w_control, w_exp, w_tie]

    fig = plt.figure(figsize=(2.6, 2.2), dpi=160)
    ax = fig.add_subplot(111)
    # 색 지정 금지 요구 없었지만, Streamlit/Matplotlib 기본 컬러를 쓰고 싶으면 colors 생략
    wedges, texts, autotexts = ax.pie(values, autopct=lambda p: f"{p:.0f}%" if p > 0 else "", startangle=90)
    ax.legend(
        wedges,
        labels,
        loc="center left",
        bbox_to_anchor=(1.0, 0.5),
        frameon=False,
        fontsize=5,
    )
    fig.tight_layout()
    return fig

def _plot_ndcg_ci(mean_diff: float, lo: float, hi: float, title: str):
    fig = plt.figure(figsize=(2.8, 2.1), dpi=160)
    ax = fig.add_subplot(111)

    ax.axhline(0.0, linewidth=1)
    ax.errorbar(
        [0], [mean_diff],
        yerr=[[mean_diff - lo], [hi - mean_diff]],
        fmt="o",
        capsize=4,
    )
    ax.set_xticks([0])
    ax.set_xticklabels(["mean(diff)"])
    ax.set_ylabel("nDCG diff", fontsize=5)
    ax.set_title(title, fontsize=10)
    ax.tick_params(axis="both", labelsize=5)
    ax.grid(True, axis="y", alpha=0.2)
    fig.tight_layout()
    return fig

def _build_ndcg_df(query_details: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(query_details).copy()
    if "qid" not in df.columns:
        df["qid"] = [f"q{i+1}" for i in range(len(df))]
    df["qid_num"] = df["qid"].astype(str).str.extract(r"(\d+)").fillna(10**9).astype(int)
    return df.sort_values("qid_num")

def _plot_ndcg_by_query(
    df: pd.DataFrame,
    control_label: str,
    exp_label: str,
):
    x = range(len(df))

    fig = plt.figure(figsize=(4.6, 2.4), dpi=150)
    ax = fig.add_subplot(111)

    ax.plot(x, df["ndcg_control"], marker="o", linewidth=1)
    ax.plot(x, df["ndcg_experimental"], marker="o", linewidth=1)

    ax.set_title("nDCG by Query", fontsize=11)
    ax.set_xticks(list(x))
    ax.set_xticklabels(df["qid"].tolist())
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("nDCG")
    ax.legend([control_label, exp_label], loc="lower left")
    ax.grid(True, axis="y", alpha=0.2)

    fig.tight_layout()
    return fig

def _plot_ndcg_diff_by_query(
    df: pd.DataFrame,
    control_label: str,
    exp_label: str,
):
    fig = plt.figure(figsize=(4.6, 2.2), dpi=150)
    ax = fig.add_subplot(111)

    ax.bar(df["qid"], df["ndcg_diff"])
    ax.axhline(0, linewidth=1)

    ax.set_title(
        f"nDCG diff by Query ({control_label} - {exp_label})",
        fontsize=11,
    )
    ax.set_ylabel("diff")
    ax.grid(True, axis="y", alpha=0.2)

    fig.tight_layout()
    return fig

# =========================================================
# Report UI blocks
# =========================================================
def _render_kpi_row(summary: dict, control_label: str, exp_label: str):
    pairwise = summary.get("pairwise") or {}
    ndcg = summary.get("ndcg") or {}

    total = summary.get("total_queries", 0)
    evaluated = summary.get("evaluated_queries", 0)

    w_control = pairwise.get("win_control", pairwise.get("win_A", 0))
    w_exp = pairwise.get("win_experimental", pairwise.get("win_B", 0))
    w_tie = pairwise.get("tie", 0)

    winrate_control = pairwise.get("winrate_control", pairwise.get("winrate_A", 0.0))
    bt_score = pairwise.get("bradley_terry_score", 0.0)
    bt_prob = pairwise.get("bradley_terry_prob_control", pairwise.get("bradley_terry_prob_A", 0.5))

    mean_diff = ndcg.get("mean_diff_control_minus_experimental", ndcg.get("mean_diff_A_minus_B", 0.0))
    ci_lo = ndcg.get("ci_95_lower", 0.0)
    ci_hi = ndcg.get("ci_95_upper", 0.0)

    # KPI: 상단을 너무 크게 만들지 말고 2줄로 나눠 깔끔하게
    r1 = st.columns(4)
    r1[0].metric("Total Queries", f"{total}")
    r1[1].metric("Evaluated", f"{evaluated}")
    r1[2].metric(f"{control_label} Wins", f"{w_control}")
    r1[3].metric(f"{exp_label} Wins", f"{w_exp}")

    r2 = st.columns(4)
    r2[0].metric(f"Winrate ({control_label})", f"{winrate_control*100:.1f}%")
    r2[1].metric("Bradley-Terry Score", f"{bt_score:.4f}")
    r2[2].metric(f"P({control_label} beats {exp_label})", f"{bt_prob*100:.1f}%")
    r2[3].metric("nDCG mean(diff)", f"{mean_diff:.4f}")

    return {
        "w_control": int(w_control),
        "w_exp": int(w_exp),
        "w_tie": int(w_tie),
        "winrate_control": float(winrate_control),
        "bt_score": float(bt_score),
        "bt_prob": float(bt_prob),
        "mean_diff": float(mean_diff),
        "ci_lo": float(ci_lo),
        "ci_hi": float(ci_hi),
    }


def _render_overview(report: dict, control_label: str, exp_label: str):
    summary = _summary_get(report)
    if not summary:
        st.error("summary가 없습니다. (결과 JSON 형식을 확인해주세요)")
        return

    stats = _render_kpi_row(summary, control_label, exp_label)

    # -------------------------
    # KPI 아래부터: 3:7 레이아웃 / 행 단위 구성
    # -------------------------
    st.divider()

    # =====================================================
    # (1) Pairwise row: 좌(타이틀+설명) / 우(차트)
    # =====================================================
    r1_l, r1_r = st.columns([4, 6], gap="large", vertical_alignment="top")

    with r1_l:
        st.markdown("### Pairwise wins")
        st.caption(
            f"""
                **쿼리 단위**로 {control_label} vs {exp_label} 결과를 맞대결로 비교합니다.  
                각 쿼리에서 더 적합한 쪽을 **승리 - Win**로 카운트하며, 동등하면 **Tie**.  
                이 차트는 전체 쿼리에서 누가 더 많이 이겼는지를 한눈에 보여줍니다.
                """
        )

    with r1_r:
        st.markdown(f"#### Pairwise Wins")
        fig_pie = _plot_pairwise_pie(
            stats["w_control"], stats["w_exp"], stats["w_tie"], control_label, exp_label
        )
        st.pyplot(fig_pie, use_container_width=False)

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    st.divider()

    # =====================================================
    # (2) nDCG row: 좌(타이틀+설명) / 우(상:CI, 하:Top/Bottom)
    # =====================================================
    r2_l, r2_r = st.columns([4, 6], gap="large", vertical_alignment="top")

    with r2_l:
        st.markdown("### nDCG")
        st.caption(
            f"""
                LLM이 각 결과 항목을 **0~5 관련도 점수로 채점 - Grading**하고,  
                그 점수로 **nDCG@k**를 계산해 랭킹 품질을 요약합니다.  
                여기서는 **diff = nDCG({control_label}) - nDCG({exp_label})** 로 비교하며,  
                95% 신뢰구간(CI)과 쿼리별 Top/Bottom을 함께 봅니다.
                """
        )

    with r2_r:
        # 우측을 위/아래로 쪼개기
        top_r, bottom_r = st.container(), st.container()

        # ---- (2-1) 우상단: 95% CI ----
        with top_r:
            st.markdown(f"#### nDCG diff (95% CI)")
            top_r1, top_r2, top_r3 = st.columns([2, 6, 2], gap="small", vertical_alignment="top")
            with top_r2:
                title = f"nDCG diff {control_label} - {exp_label} (95% CI)"
                fig_ci = _plot_ndcg_ci(stats["mean_diff"], stats["ci_lo"], stats["ci_hi"], title)
                st.pyplot(fig_ci, use_container_width=False)

        st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)

        # ---- (2-2) 우하단: Top/Bottom 테이블 ----
        with bottom_r:
            st.markdown(f"#### nDCG diff Top/Bottom ( {control_label} 기준 )")
            st.caption(f"diff = nDCG({control_label}) - nDCG({exp_label})")

            qd = report.get("query_details", []) or []
            if not qd:
                st.info("query_details가 없어 Top/Bottom을 표시할 수 없습니다.")
            else:
                df_ndcg = _build_ndcg_df(qd)

                # 스키마 호환
                if "ndcg_control" not in df_ndcg.columns and "ndcg_A" in df_ndcg.columns:
                    df_ndcg["ndcg_control"] = df_ndcg["ndcg_A"]
                if "ndcg_experimental" not in df_ndcg.columns and "ndcg_B" in df_ndcg.columns:
                    df_ndcg["ndcg_experimental"] = df_ndcg["ndcg_B"]

                if "ndcg_diff" not in df_ndcg.columns:
                    df_ndcg["ndcg_diff"] = df_ndcg["ndcg_control"] - df_ndcg["ndcg_experimental"]

                t_l, t_r = st.columns(2, gap="large")

                with t_l:
                    st.caption(f"👍 {control_label} 우세 (Top 5)")
                    top_control = (
                        df_ndcg.nlargest(5, "ndcg_diff")[["qid", "query", "ndcg_diff"]]
                        .rename(columns={"ndcg_diff": f"diff({control_label}-{exp_label})"})
                        .copy()
                    )
                    st.dataframe(top_control, use_container_width=True, hide_index=True)

                with t_r:
                    st.caption(f"👎 {control_label} 열세 (Bottom 5)")
                    bot_control = (
                        df_ndcg.nsmallest(5, "ndcg_diff")[["qid", "query", "ndcg_diff"]]
                        .rename(columns={"ndcg_diff": f"diff({control_label}-{exp_label})"})
                        .copy()
                    )
                    st.dataframe(bot_control, use_container_width=True, hide_index=True)

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    st.divider()

    # =====================================================
    # (3) Detail interpretation row: 좌(타이틀) / 우(가독성 있게 카드/불릿)
    # =====================================================
    r3_l, r3_r = st.columns([4, 6], gap="large", vertical_alignment="top")

    with r3_l:
        st.markdown("### 상세 해석")
        st.caption(
            """
            Pairwise / Bradley–Terry / nDCG 결과를 종합해  
            “어느 쪽이 더 좋아 보이는지”와 “통계적으로 확실한지”를 정리합니다.
            """
        )

    with r3_r:
        mean_diff = stats["mean_diff"]
        ci_lo, ci_hi = stats["ci_lo"], stats["ci_hi"]
        w_control, w_exp, w_tie = stats["w_control"], stats["w_exp"], stats["w_tie"]
        bt_score = stats["bt_score"]
        bt_prob = stats["bt_prob"]

        # nDCG 해석
        if ci_lo > 0:
            ndcg_verdict = f"{control_label}가 nDCG에서 **유의미하게 우세**할 가능성이 큽니다."
            ndcg_hint = "95% CI가 0보다 큼"
        elif ci_hi < 0:
            ndcg_verdict = f"{exp_label}가 nDCG에서 **유의미하게 우세**할 가능성이 큽니다."
            ndcg_hint = "95% CI가 0보다 작음"
        else:
            ndcg_verdict = "nDCG 차이는 **유의미하다고 보기 어렵습니다.**"
            ndcg_hint = "95% CI가 0을 포함"

        # BT 해석
        if bt_score > 0:
            bt_verdict = f"상대강도 추정 기준으로 **{control_label} 우세**"
        elif bt_score < 0:
            bt_verdict = f"상대강도 추정 기준으로 **{exp_label} 우세**"
        else:
            bt_verdict = "상대강도 기준 **우열 거의 없음**"

        # Pairwise 리드
        if w_exp > w_control:
            lead = exp_label
        elif w_control > w_exp:
            lead = control_label
        else:
            lead = "우세 없음"

        # ---- 가독성: 카드처럼 섹션 분리 ----
        st.markdown(
            f"""
    <div style="padding:14px; border:1px solid rgba(49,51,63,0.15); border-radius:14px; margin-bottom:10px;">
      <div style="font-weight:700; margin-bottom:6px;">① Pairwise(맞대결) 요약</div>
      <div style="line-height:1.7;">
        • 전체 경향: <b>{lead}</b><br/>
        • 승/패/무: {control_label} <b>{w_control}</b> / {exp_label} <b>{w_exp}</b> / tie <b>{w_tie}</b>
      </div>
    </div>

    <div style="padding:14px; border:1px solid rgba(49,51,63,0.15); border-radius:14px; margin-bottom:10px;">
      <div style="font-weight:700; margin-bottom:6px;">② Bradley–Terry(상대강도) 요약</div>
      <div style="line-height:1.7;">
        • 결론: {bt_verdict}<br/>
        • score: <b>{bt_score:.4f}</b><br/>
        • {control_label} 승률 추정: <b>{bt_prob * 100:.1f}%</b>
      </div>
    </div>

    <div style="padding:14px; border:1px solid rgba(49,51,63,0.15); border-radius:14px;">
      <div style="font-weight:700; margin-bottom:6px;">③ nDCG(채점 기반 랭킹 품질) 요약</div>
      <div style="line-height:1.7;">
        • 평균 diff({control_label}-{exp_label}): <b>{mean_diff:.4f}</b><br/>
        • 95% CI: <b>[{ci_lo:.4f}, {ci_hi:.4f}]</b> <span style="opacity:0.75;">({ndcg_hint})</span><br/>
        • 결론: {ndcg_verdict}
      </div>
    </div>
                """,
            unsafe_allow_html=True,
        )
    st.divider()

    # =====================================================
    # (4) Detail LLM Analyzed interpretation row: 좌(타이틀) / 우(가독성 있게 카드/불릿)
    # =====================================================
    r4_l, r4_r = st.columns([4, 6], gap="large", vertical_alignment="top")

    with r4_l:
        st.markdown("### LLM Analyzed Report")
        st.caption(
            """
            Pairwise / Bradley–Terry / nDCG 결과를 종합해 LLM 을 통해 분석합니다.
            결과를 원하시면 오른쪽 분석 생성 버튼을 눌러주세요.
            """
        )

    with r4_r:
        st.markdown("### ")

        st.session_state.setdefault("llm_analysis_cache_md", {})  # {path: markdown}

        selected_path = st.session_state.get("results_selected_path")
        cache_md = st.session_state.llm_analysis_cache_md

        colA, colB = st.columns([0.8, 0.2])
        with colB:
            run_analysis = st.button("분석 생성", type="primary", use_container_width=True)

        report_md = cache_md.get(selected_path) if selected_path else None

    if run_analysis:
        with st.spinner("LLM이 결과를 한국어로 분석 중입니다..."):
            llm_client = GeminiClient()
            report_md = analyze_report_with_llm(report, control_label, exp_label, llm_client)
            report_md_unwrap = unwrap_markdown(report_md)
            if selected_path:
                cache_md[selected_path] = report_md
                st.session_state.llm_analysis_cache_md = cache_md

    if report_md:
        st.markdown(report_md_unwrap)
    else:
        st.info("‘분석 생성’을 누르면, LLM 을 통한 보다 자세한 한국어 결과 해석 리포트를 생성합니다.")


def _render_pairwise_detail(report: dict, control_label: str, exp_label: str):
    rows = report.get("pairwise_results") or []
    if not rows:
        st.info("pairwise_results가 없습니다.")
        return

    df = pd.DataFrame(rows).copy()
    # winner(A/B/tie) -> 라벨
    df["winner_label"] = df["winner"].apply(lambda w: _winner_to_label(w, control_label, exp_label))
    # 보기 좋게 정렬(qid 숫자 정렬)
    def _qid_key(qid: str) -> int:
        try:
            return int(str(qid).lstrip("q"))
        except Exception:
            return 10**9
    df = df.sort_values(by="qid", key=lambda s: s.map(_qid_key))

    st.markdown("### Pairwise 쿼리별 승패")
    st.caption("winner는 내부적으로 A/B/tie로 저장되며, A=Control / B=Experimental로 해석합니다.")
    st.dataframe(
        df[["qid", "query", "winner_label", "confidence", "reason"]],
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    # 간단 집계 테이블
    agg = df["winner_label"].value_counts().reset_index()
    agg.columns = ["winner", "count"]
    st.markdown("### Pairwise 집계")
    st.dataframe(agg, use_container_width=True, hide_index=True)


def _render_ndcg_detail(report: dict, control_label: str, exp_label: str):
    rows = report.get("query_details") or []
    if not rows:
        st.info("query_details가 없습니다.")
        return

    # ✅ 1) 공통 DF 빌드 (qid 정렬 포함)
    df = _build_ndcg_df(rows)

    # ✅ 2) 스키마 호환 (예시: ndcg_control / ndcg_experimental vs ndcg_A / ndcg_B)
    if "ndcg_control" not in df.columns and "ndcg_A" in df.columns:
        df["ndcg_control"] = df["ndcg_A"]
    if "ndcg_experimental" not in df.columns and "ndcg_B" in df.columns:
        df["ndcg_experimental"] = df["ndcg_B"]

    # diff도 마찬가지
    if "ndcg_diff" not in df.columns and ("ndcg_control" in df.columns and "ndcg_experimental" in df.columns):
        df["ndcg_diff"] = df["ndcg_control"] - df["ndcg_experimental"]

    st.markdown("### nDCG 쿼리별 상세")
    st.caption("각 쿼리에 대해 LLM이 항목별 관련도(0~5)를 채점 → nDCG@k로 요약한 결과입니다.")

    # ✅ 3) (NEW) 차트 2개를 표 상단에 배치
    ch1, ch2 = st.columns([1, 1], gap="large")
    with ch1:
        fig1 = _plot_ndcg_by_query(df, control_label, exp_label)
        st.pyplot(fig1, use_container_width=True)
    with ch2:
        fig2 = _plot_ndcg_diff_by_query(df, control_label, exp_label)
        st.pyplot(fig2, use_container_width=True)

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # ✅ 4) 테이블
    show_cols = [c for c in ["qid", "query", "ndcg_control", "ndcg_experimental", "ndcg_diff"] if c in df.columns]
    st.dataframe(df[show_cols], use_container_width=True, hide_index=True)

    st.divider()

    # ✅ 5) 쿼리 선택 후 grades/notes 확인 (기존 그대로)
    st.markdown("### 쿼리별 Grading(0~5) 확인")
    # 표시용 옵션 생성: "q1 - 냉장고"
    options = [
        f'{r["qid"]} - {r["query"]}'
        for _, r in df[["qid", "query"]].iterrows()
    ]

    picked_label = st.selectbox(
        "쿼리 선택",
        options,
        index=0,
    )

    # 실제 qid 추출 ("q1 - 냉장고" → "q1")
    picked_qid = picked_label.split(" - ", 1)[0]

    row = df[df["qid"] == picked_qid].iloc[0].to_dict()

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown(f"**{control_label} grades / notes**")
        st.json({
            "grades": row.get("grades_control") or row.get("grades_A"),
            "notes": row.get("notes_control") or row.get("notes_A"),
        })
    with c2:
        st.markdown(f"**{exp_label} grades / notes**")
        st.json({
            "grades": row.get("grades_experimental") or row.get("grades_B"),
            "notes": row.get("notes_experimental") or row.get("notes_B"),
        })


# =========================================================
# Main report render
# =========================================================
def _render_report(report_path: str):
    report = _read_json(report_path)
    st.session_state.results_loaded_obj = report  # 캐시

    summary = _summary_get(report)
    pairwise = summary.get("pairwise") or {}
    control_label, exp_label = _infer_labels(pairwise)

    # 상단 헤더 (Back + 파일명)
    top = st.columns([0.80, 0.20], vertical_alignment="center")
    with top[0]:
        st.markdown(
            f"## Test Result Report\n"
            f"<div style='color:rgba(30,35,40,0.65); font-size:13px;'>"
            f"{Path(report_path).name}"
            f"</div>",
            unsafe_allow_html=True,
        )
    with top[1]:
        if st.button("Back to list", use_container_width=True):
            _reset_state_to_list()
            st.rerun()

    st.divider()

    st.markdown(
        f"""
    <div style="
      padding:14px 16px;
      border:1px solid rgba(0,0,0,0.08);
      border-radius:14px;
      background:rgba(248,249,251,0.9);
      line-height:1.65;
    ">
      <div style="font-size:14px; font-weight:700; margin-bottom:8px;">
        LLM-as-a-Judge 해석 가이드
      </div>
      <div style="font-size:13px; color:rgba(30,35,40,0.80);">
        • <b>Pairwise</b>: LLM이 <b>{control_label}</b> vs <b>{exp_label}</b> 상위 k개를 비교해 승/패/무를 결정합니다.<br/>
        • <b>Winrate</b>: 무승부를 제외한 승부 기준으로 <b>{control_label}</b>의 승률입니다.<br/>
        • <b>Bradley–Terry</b>: 여러 쿼리의 승패를 하나의 상대강도로 요약합니다. (Score&gt;0이면 {control_label} 우세)<br/>
        • <b>Grading → nDCG</b>: 각 결과를 0~5로 채점하고, 랭킹 품질을 nDCG@k로 계산합니다.<br/>
        • <b>95% CI</b>: nDCG diff의 신뢰구간이며, 0을 포함하면 유의미한 차이로 단정하기 어렵습니다.
      </div>
    </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    # ✅ 1/2/3 넘기면서 보기 (탭)
    # - 탭 선택 상태 유지
    tabs = ["1) Overview", "2) Pairwise Detail", "3) nDCG Detail"]
    st.session_state.setdefault("results_active_tab", tabs[0])

    # 1) default 값이 tabs에 없는 경우를 방어
    if st.session_state.results_active_tab not in tabs:
        st.session_state.results_active_tab = tabs[0]

    # 2) 선택 UI (key 고정)
    try:
        picked = st.segmented_control(
            "보기",
            options=tabs,
            selection_mode="single",
            default=st.session_state.results_active_tab,
            key="results_tab_picker",  # ✅ key 고정
        )
    except Exception:
        picked = st.radio(
            "보기",
            tabs,
            horizontal=True,
            index=tabs.index(st.session_state.results_active_tab),
            key="results_tab_picker_radio",  # ✅ key 고정
        )

    # 3) 선택 결과 반영
    st.session_state.results_active_tab = picked

    st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)

    # 4) 분기 렌더
    if picked == tabs[0]:
        _render_overview(report, control_label, exp_label)
    elif picked == tabs[1]:
        _render_pairwise_detail(report, control_label, exp_label)
    else:
        _render_ndcg_detail(report, control_label, exp_label)

    st.divider()


# =========================================================
# List render
# =========================================================
def _render_list():
    st.markdown("## Results")
    st.caption("test_results 폴더에 저장된 실행 결과를 선택해 리포트를 확인합니다.")
    st.divider()

    base_dir = _results_dir()
    files = sorted(base_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not files:
        st.info("test_results 폴더에 결과 JSON이 없습니다.")
        return

    rows = []
    for p in files:
        stat = p.stat()
        rows.append({
            "Name": p.name,
            "Created": _fmt_dt(stat.st_mtime),
            "Size": round(stat.st_size / 1024, 1),  # KB
            "path": str(p),
            "mtime": stat.st_mtime,
        })

    df = pd.DataFrame(rows, columns=["Name", "Created", "Size", "path", "mtime"])

    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(sortable=True, filter=True, resizable=True)
    gb.configure_selection(selection_mode="single", use_checkbox=True)
    gb.configure_column("Name", headerName="Result File", width=560, checkboxSelection=True)
    gb.configure_column("Created", headerName="Created", width=180)
    gb.configure_column("Size", headerName="Size(KB)", width=110)
    gb.configure_column("path", hide=True)
    gb.configure_column("mtime", hide=True)
    gb.configure_pagination(enabled=True, paginationAutoPageSize=False, paginationPageSize=5)

    grid_options = gb.build()
    grid_options["rowSelection"] = "single"
    grid_options["suppressRowClickSelection"] = False
    grid_options["rowMultiSelectWithClick"] = False

    grid_response = AgGrid(
        df,
        gridOptions=grid_options,
        height=303,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        fit_columns_on_grid_load=True,
        theme="balham",
        key="results_grid",
    )

    picked_path = None
    selected_rows = grid_response.get("selected_rows", [])
    if isinstance(selected_rows, list) and selected_rows:
        picked_path = selected_rows[0].get("path")
    elif isinstance(selected_rows, pd.DataFrame) and not selected_rows.empty:
        picked_path = selected_rows.iloc[0].get("path")

    st.session_state.results_selected_path = picked_path

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

    disabled = picked_path is None
    if st.button("📄 리포트 열기", type="primary", use_container_width=True, disabled=disabled):
        st.session_state.results_mode = "report"
        st.rerun()


# =========================================================
# Page entry
# =========================================================
def render():
    _init_state()

    # ✅ 핵심: report 모드면 “grid 없이 리포트만” 렌더
    if st.session_state.results_mode == "report":
        path = st.session_state.results_selected_path
        if not path:
            # 예외: report 모드인데 선택 파일이 없으면 list로 복귀
            _reset_state_to_list()
            st.rerun()
        _render_report(path)
        return

    # list 모드
    _render_list()