"""Minimax value of one additional recoverable sample statistic."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

import numpy as np

from .empirical import EmpiricalProblem


@dataclass(frozen=True)
class QuestionScore:
    question: str
    cut_index: int
    feasible_answer_min: int
    feasible_answer_max: int
    baseline_total_width: float
    worst_case_residual_width: float
    minimax_width_reduction: float
    cost: float
    score_per_cost: float
    feasible_answers_evaluated: int
    reporting_variants_considered: int = 1

    def as_dict(self) -> dict[str, object]:
        return {
            "question": self.question,
            "cut_index": self.cut_index,
            "feasible_answer_range": [self.feasible_answer_min, self.feasible_answer_max],
            "baseline_total_width": self.baseline_total_width,
            "worst_case_residual_width": self.worst_case_residual_width,
            "minimax_width_reduction": self.minimax_width_reduction,
            "cost": self.cost,
            "score_per_cost": self.score_per_cost,
            "feasible_answers_evaluated": self.feasible_answers_evaluated,
            "reporting_variants_considered": self.reporting_variants_considered,
        }


def _rank_robust_tail_count_questions_lp(
    *,
    problems: dict[str, EmpiricalProblem],
    target_objectives: list[np.ndarray],
    exclude_direct_targets: bool = False,
    costs: dict[str, float] | None = None,
    time_limit_seconds: float | None = None,
) -> list[QuestionScore]:
    """Exact minimax question ranking over a declared reporting envelope."""
    deadline = _deadline(time_limit_seconds)
    if not problems or not target_objectives:
        return []
    problem_list = list(problems.values())
    reference_problem = problem_list[0]
    if any(
        problem.n != reference_problem.n or problem.k != reference_problem.k
        for problem in problem_list
    ):
        raise ValueError("reporting-envelope problems must share n and panel geometry")
    targets = [np.asarray(item, dtype=float) for item in target_objectives]
    baseline_width = 0.0
    for target in targets:
        bounds = [problem.bounds(target) for problem in problem_list]
        baseline_width += (
            max(upper.fraction for _, upper in bounds)
            - min(lower.fraction for lower, _ in bounds)
        )
    scores: list[QuestionScore] = []
    costs = costs or {}
    for cut_index in range(reference_problem.k - 1):
        _check_deadline(deadline, scores)
        candidate = np.zeros(reference_problem.k)
        candidate[cut_index + 1 :] = 1.0
        if exclude_direct_targets and any(np.array_equal(candidate, target) for target in targets):
            continue
        candidate_bounds = [problem.bounds(candidate) for problem in problem_list]
        answer_min = min(lower.count for lower, _ in candidate_bounds)
        answer_max = max(upper.count for _, upper in candidate_bounds)
        worst_residual = 0.0
        feasible_answers = 0
        for answer in range(answer_min, answer_max + 1):
            _check_deadline(deadline, scores)
            conditional: list[EmpiricalProblem] = []
            for problem, (lower, upper) in zip(problem_list, candidate_bounds):
                if answer < lower.count or answer > upper.count:
                    continue
                try:
                    conditional.append(problem.with_equality(candidate, answer))
                except ValueError:
                    continue
            if not conditional:
                continue
            feasible_answers += 1
            residual = 0.0
            for target in targets:
                conditioned_bounds = [problem.bounds(target) for problem in conditional]
                residual += (
                    max(upper.fraction for _, upper in conditioned_bounds)
                    - min(lower.fraction for lower, _ in conditioned_bounds)
                )
            worst_residual = max(worst_residual, residual)
        if feasible_answers == 0:
            continue
        question = (
            "How many isolates had recorded MIC above "
            f"category {reference_problem.panel.bins[cut_index].label} (all subsequent panel categories)?"
        )
        cost = float(costs.get(question, costs.get(question.replace("category ", "").replace(" (all subsequent panel categories)", ""), 1.0)))
        if not np.isfinite(cost) or cost <= 0:
            raise ValueError("Question acquisition costs must be positive")
        reduction = max(0.0, baseline_width - worst_residual)
        scores.append(
            QuestionScore(
                question=question,
                cut_index=cut_index,
                feasible_answer_min=answer_min,
                feasible_answer_max=answer_max,
                baseline_total_width=baseline_width,
                worst_case_residual_width=worst_residual,
                minimax_width_reduction=reduction,
                cost=cost,
                score_per_cost=reduction / cost,
                feasible_answers_evaluated=feasible_answers,
                reporting_variants_considered=len(problem_list),
            )
        )
    return sorted(
        scores,
        key=lambda item: (item.score_per_cost, item.minimax_width_reduction, -item.cut_index),
        reverse=True,
    )


class QuestionSearchTimeout(TimeoutError):
    def __init__(self, completed_scores):
        super().__init__("Question search time budget exhausted; optimum is unverified")
        self.completed_scores = list(completed_scores)


def _deadline(seconds):
    if seconds is None:
        return None
    if not np.isfinite(seconds) or seconds < 0:
        raise ValueError("time_limit_seconds must be finite and nonnegative")
    return monotonic() + float(seconds)


def _check_deadline(deadline, scores):
    if deadline is not None and monotonic() >= deadline:
        raise QuestionSearchTimeout(scores)


def _prefix_distances(problem):
    """Closure of integer difference constraints on F_0,...,F_K.

    An interval row bounds F_b-F_a. Nonnegative cells give F_i<=F_(i+1).
    Shortest paths therefore give exact differences, including integral extrema.
    """
    k=problem.k
    dist=np.full((k+1,k+1),np.inf)
    np.fill_diagonal(dist,0.)
    for i in range(k):
        dist[i+1,i]=0.
    matrix,lower,upper=problem.linear_constraints
    for row,lo,hi in zip(matrix,lower,upper):
        support=np.flatnonzero(row)
        if not len(support):
            continue
        a,b=int(support[0]),int(support[-1]+1)
        if np.isfinite(hi): dist[a,b]=min(dist[a,b],hi)
        if np.isfinite(lo): dist[b,a]=min(dist[b,a],-lo)
    for via in range(k+1):
        dist=np.minimum(dist,dist[:,via,None]+dist[None,via,:])
    if np.any(np.diag(dist)<-1e-9):
        raise ValueError("Incompatible cumulative-count constraints")
    return np.rint(dist)


def _contiguous_interval(target,k):
    """Return (s,t) when target is one contiguous block of ones over categories s..t-1, else None."""
    if target.shape!=(k,) or not np.all(np.isin(target,[0.,1.])):
        return None
    ones=np.flatnonzero(target)
    if not len(ones) or ones[-1]-ones[0]+1!=len(ones):
        return None
    return int(ones[0]),int(ones[-1])+1


def _rank_interval_count_questions(values,intervals,*,exclude_direct_targets,costs,deadline):
    """Exact minimax ranking for contiguous-range targets by difference-constraint closure.

    A range s..t-1 has count F_t-F_s, bounded by -D[t,s] and D[s,t]. Conditioning on
    F_q=a adds the edges 0->q (weight a) and q->0 (weight -a); the closed bound becomes
    min(D[s,t], D[s,0]+a+D[q,t], D[s,q]-a+D[0,t]) and symmetrically for the lower side.
    Across variants the admissible answers and extrema are united, as for tail targets.
    """
    base=values[0]; scores=[]
    _check_deadline(deadline,scores)
    distances=[_prefix_distances(p) for p in values]
    s=np.array([a for a,b in intervals]); t=np.array([b for a,b in intervals])
    lower=np.min(np.stack([-d[t,s] for d in distances]),axis=0)
    upper=np.max(np.stack([d[s,t] for d in distances]),axis=0)
    baseline=float(np.sum(upper-lower))/base.n
    costs=costs or {}
    for q in range(1,base.k):
        _check_deadline(deadline,scores)
        if exclude_direct_targets and any(b==base.k and a==q or a==0 and b==q for a,b in intervals):continue
        ranges=[(int(-d[q,0]),int(d[0,q])) for d in distances]
        first=min(lo for lo,hi in ranges);last=max(hi for lo,hi in ranges)
        worst_count_width=0.; evaluated=0
        for start in range(first,last+1,100000):
            _check_deadline(deadline,scores)
            answers=np.arange(start,min(start+100000,last+1),dtype=float)
            lo_union=np.full((len(answers),len(s)),np.inf)
            hi_union=np.full_like(lo_union,-np.inf)
            valid_any=np.zeros(len(answers),dtype=bool)
            for d,(lo,hi) in zip(distances,ranges):
                valid=(answers>=lo)&(answers<=hi)
                a=answers[valid,None]
                high=np.minimum(np.minimum(d[s,t],d[s,0]+a+d[q,t]),d[s,q]-a+d[0,t])
                low=-np.minimum(np.minimum(d[t,s],d[t,0]+a+d[q,s]),d[t,q]-a+d[0,s])
                lo_union[valid]=np.minimum(lo_union[valid],low)
                hi_union[valid]=np.maximum(hi_union[valid],high)
                valid_any |= valid
            evaluated+=int(valid_any.sum())
            if valid_any.any():
                worst_count_width=max(worst_count_width,float(np.max(np.sum(hi_union[valid_any]-lo_union[valid_any],axis=1))))
        if not evaluated:continue
        question=f"How many isolates had recorded MIC above category {base.panel.bins[q-1].label} (all subsequent panel categories)?"
        cost=float(costs.get(question,costs.get(f"How many isolates had recorded MIC above {base.panel.bins[q-1].label}?",1.)))
        if not np.isfinite(cost) or cost<=0:raise ValueError("Question acquisition costs must be positive")
        residual=worst_count_width/base.n;gain=max(0.,baseline-residual)
        scores.append(QuestionScore(question=question,cut_index=q-1,
            feasible_answer_min=base.n-last,feasible_answer_max=base.n-first,
            baseline_total_width=baseline,worst_case_residual_width=residual,
            minimax_width_reduction=gain,cost=cost,score_per_cost=gain/cost,
            feasible_answers_evaluated=evaluated,reporting_variants_considered=len(values)))
    return sorted(scores,key=lambda s:(s.score_per_cost,s.minimax_width_reduction,-s.cut_index),reverse=True)


def rank_tail_count_questions(*,problem,target_objectives,exclude_direct_targets=False,
                              costs=None,time_limit_seconds=None):
    return rank_robust_tail_count_questions(problems={"primary":problem},
                target_objectives=target_objectives,exclude_direct_targets=exclude_direct_targets,
                costs=costs,time_limit_seconds=time_limit_seconds)


def rank_robust_tail_count_questions(*,problems,target_objectives,exclude_direct_targets=False,
                                     costs=None,time_limit_seconds=None):
    """Exact minimax over integer answers, using cumulative-constraint closure.

    Condition F_q=a. For any prefix j its exact bounds become
    max(-D[j,0], a-D[j,q]) and min(D[0,j], a+D[q,j]). This is the
    shortest-path closure after adding the two equality edges. Across variants
    the admissible answer domains and extrema are united, never averaged.
    Noncanonical problems retain the independently tested LP implementation.
    """
    deadline=_deadline(time_limit_seconds)
    if not problems or not target_objectives:return []
    values=list(problems.values()); base=values[0]; targets=[np.asarray(t,dtype=float) for t in target_objectives]
    if any(p.n!=base.n or p.panel!=base.panel for p in values):
        raise ValueError("reporting-envelope problems must share n and panel geometry")
    canonical=all(p._canonical_tu and p._integral_rhs for p in values)
    intervals=[_contiguous_interval(t,base.k) for t in targets]
    if canonical and all(interval is not None for interval in intervals) and not all(
            np.all(np.diff(t)>=0) for t in targets):
        return _rank_interval_count_questions(values,intervals,exclude_direct_targets=exclude_direct_targets,
                 costs=costs,deadline=deadline)
    canonical=canonical and all(t.shape==(base.k,) and np.all(np.isin(t,[0.,1.])) and np.all(np.diff(t)>=0) for t in targets)
    if not canonical:
        return _rank_robust_tail_count_questions_lp(problems=problems,target_objectives=targets,
                 exclude_direct_targets=exclude_direct_targets,costs=costs,time_limit_seconds=time_limit_seconds)
    scores=[]
    _check_deadline(deadline,scores)
    distances=[_prefix_distances(p) for p in values]
    cuts=np.array([int(np.flatnonzero(t)[0]) if np.any(t) else base.k for t in targets])
    lower=np.min(np.stack([-d[cuts,0] for d in distances]),axis=0)
    upper=np.max(np.stack([d[0,cuts] for d in distances]),axis=0)
    baseline=float(np.sum(upper-lower))/base.n
    costs=costs or {}
    for q in range(1,base.k):
        _check_deadline(deadline,scores)
        if exclude_direct_targets and q in cuts:continue
        ranges=[(int(-d[q,0]),int(d[0,q])) for d in distances]
        first=min(lo for lo,hi in ranges);last=max(hi for lo,hi in ranges)
        worst_count_width=0.; evaluated=0
        # Chunked to keep large-n memory bounded. Every feasible answer still counts.
        for start in range(first,last+1,100000):
            _check_deadline(deadline,scores)
            answers=np.arange(start,min(start+100000,last+1),dtype=float)
            lo_union=np.full((len(answers),len(cuts)),np.inf)
            hi_union=np.full_like(lo_union,-np.inf)
            valid_any=np.zeros(len(answers),dtype=bool)
            for d,(lo,hi) in zip(distances,ranges):
                valid=(answers>=lo)&(answers<=hi)
                a=answers[valid,None]
                low=np.maximum(-d[cuts,0],a-d[cuts,q])
                high=np.minimum(d[0,cuts],a+d[q,cuts])
                lo_union[valid]=np.minimum(lo_union[valid],low)
                hi_union[valid]=np.maximum(hi_union[valid],high)
                valid_any |= valid
            evaluated+=int(valid_any.sum())
            if valid_any.any():
                worst_count_width=max(worst_count_width,float(np.max(np.sum(hi_union[valid_any]-lo_union[valid_any],axis=1))))
        if not evaluated:continue
        question=f"How many isolates had recorded MIC above category {base.panel.bins[q-1].label} (all subsequent panel categories)?"
        cost=float(costs.get(question,costs.get(f"How many isolates had recorded MIC above {base.panel.bins[q-1].label}?",1.)))
        if not np.isfinite(cost) or cost<=0:raise ValueError("Question acquisition costs must be positive")
        residual=worst_count_width/base.n;gain=max(0.,baseline-residual)
        scores.append(QuestionScore(question=question,cut_index=q-1,
            feasible_answer_min=base.n-last,feasible_answer_max=base.n-first,
            baseline_total_width=baseline,worst_case_residual_width=residual,
            minimax_width_reduction=gain,cost=cost,score_per_cost=gain/cost,
            feasible_answers_evaluated=evaluated,reporting_variants_considered=len(values)))
    return sorted(scores,key=lambda s:(s.score_per_cost,s.minimax_width_reduction,-s.cut_index),reverse=True)
