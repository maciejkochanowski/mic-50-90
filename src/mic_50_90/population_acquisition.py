"""Bounded exact search for original-sample counts meeting population precision.

States retain complete integer difference-constraint closures for each reporting
variant. A node is sufficient only if certified population projections satisfy
the target. The search never counts an unfinished projection as failure.
"""
from __future__ import annotations

from fractions import Fraction
from math import isfinite
from time import monotonic

import numpy as np

from .joint_population import population_distribution, _validate
from .population_precision import maximum_population_partition
from .utility import _prefix_distances
from .validation import exact_integer, decimal_number


def plan_population_precision(problems, *, precision_pp, confidence_level=.95,
        method='bonferroni', minimum_bins=None, required_cuts=(), queries=None,
        time_limit_seconds=10., projection_time_limit_seconds=1., max_states=1000):
    n,k = _validate(problems)
    panel = next(iter(problems.values())).panel
    precision = decimal_number(precision_pp, 'population_precision_pp')
    if not 0 <= precision <= 100:
        raise ValueError('population_precision_pp must lie in [0,100]')
    confidence = decimal_number(confidence_level, 'confidence_level')
    if not 0 < confidence < 1:
        raise ValueError('confidence_level must lie strictly between 0 and 1')
    required_cuts = tuple(exact_integer(c, 'required cut', 1) for c in required_cuts)
    if any(c >= k for c in required_cuts):
        raise ValueError('Required cuts must be interior panel boundaries')
    wanted = k if minimum_bins is None else exact_integer(minimum_bins,'minimum_bins',1)
    if wanted > k:
        raise ValueError('minimum_bins exceeds the original number of categories')
    if not isfinite(time_limit_seconds) or time_limit_seconds < 0:
        raise ValueError('Planning time must be finite and nonnegative')
    max_states = exact_integer(max_states,'max_states',1)
    if method not in {'bonferroni','joint-exact','range-calibrated','range-hunter'}:
        raise ValueError('Unknown fixed population method')
    metadata = dict(n=n, minimum_bins=wanted, precision_pp=float(precision),
        precision_pp_text=str(precision), confidence_level=float(confidence), method=method,
        scope='Worst-case cost of counts from these same isolates. A failed universal plan does not mean every compatible histogram fails.')
    if queries is None:
        queries = [dict(start_index=a,stop_index=b,cost=1) for a in range(k) for b in range(a+1,k+1) if (a,b)!=(0,k)]
    allowed = []
    for q in queries:
        a,b = exact_integer(q['start_index'],'start_index',0),exact_integer(q['stop_index'],'stop_index',1)
        cost = Fraction(str(q.get('cost',1)))
        if not 0 <= a < b <= k or (a,b)==(0,k) or cost <= 0:
            raise ValueError('Queries require a proper contiguous interval and a positive cost')
        allowed.append((a,b,cost))
    start = monotonic(); deadline = start+time_limit_seconds
    visited, cache = 0, {}
    root_best = None
    full_failure = None
    def check():
        if monotonic() >= deadline:
            raise TimeoutError
    def assess(state):
        check()
        pop = population_distribution(state,method=method,confidence_level=confidence_level,
            include_intervals=True,time_limit_seconds=min(projection_time_limit_seconds,max(0,deadline-monotonic())),
            **({'width_target_pp':precision} if method=='range-hunter' else {}))
        resolution = maximum_population_partition(pop,panel,precision_pp=precision_pp,required_cuts=required_cuts)
        check()
        return resolution
    def solve(state, root=False):
        nonlocal visited, root_best
        check()
        matrices = {key:_prefix_distances(p) for key,p in state.items()}
        signature = tuple(sorted(set(tuple(map(tuple,m)) for m in matrices.values())))
        if signature in cache:
            return cache[signature]
        if visited >= max_states:
            raise TimeoutError
        visited += 1
        resolution = assess(state)
        if resolution['guaranteed_number_of_bins'] >= wanted:
            result = (Fraction(0),dict(goal_reached=True,resolution=resolution),True)
            cache[signature] = result
            return result
        uncertain = resolution['possible_number_of_bins'] >= wanted
        best, plan, complete = None,None,not uncertain
        usable = False
        for a,b,cost in sorted(allowed,key=lambda q:(q[2],q[0],q[1])):
            check()
            domains = set()
            for m in matrices.values():
                domains.update(range(int(-m[b,a]),int(m[a,b])+1))
            if len(domains) <= 1:
                continue
            usable = True
            if best is not None and cost >= best:
                continue  # Every child has nonnegative cost.
            objective = np.zeros(k); objective[a:b] = 1
            answers, worst, feasible, finished = {},Fraction(0),True,True
            for count in sorted(domains):
                check()
                child = {}
                for key,p in state.items():
                    try:
                        child[key] = p.with_count_interval(objective,count,count)
                    except ValueError:
                        pass
                if not child:
                    continue
                subcost, subtree, subcomplete = solve(child)
                finished = finished and subcomplete
                if subcost is None:
                    feasible = False
                    if subcomplete:
                        break
                else:
                    worst = max(worst,subcost)
                    answers[str(count)] = subtree
            complete = complete and finished
            if feasible and (best is None or cost+worst < best):
                best = cost+worst
                plan = dict(goal_reached=False,query=dict(start_index=a,stop_index=b,
                    start_category=panel.labels[a],end_category=panel.labels[b-1],cost=str(cost)),answers=answers)
                if root:
                    root_best = (best,plan)
        if not usable:
            complete = not uncertain
        result = (best,plan,complete)
        cache[signature] = result
        return result
    try:
        check()
        # A single compatible full histogram that fails is a certificate that
        # no policy can guarantee the goal for EVERY possible returned answer.
        for p in problems.values():
            check()
            h = p.bounds(np.zeros(k))[0].histogram
            full = p
            for j,count in enumerate(h):
                v = np.zeros(k);v[j]=1
                full = full.with_count_interval(v,int(count),int(count))
            r = assess({'full':full})
            if r['possible_number_of_bins'] < wanted:
                full_failure = dict(histogram=list(map(int,h)),resolution=r)
                return dict(**metadata, status='no_guaranteed_plan',plan=None,cost_lower=None,cost_upper=None,
                    optimality_verified=True,full_counts_failure_witness=full_failure,
                    all_histograms_impossible_claimed=False,states_evaluated=visited,elapsed_seconds=monotonic()-start)
        cost,plan,complete = solve(problems,root=True)
        status = ('achieved' if cost==0 else 'achievable_with_counts') if cost is not None else ('no_guaranteed_plan' if complete else 'numerically_unresolved')
    except (TimeoutError,MemoryError):
        cost,plan = root_best if root_best else (None,None)
        complete = False
        status = 'achievable_with_counts' if plan is not None else 'numerically_unresolved'
    return dict(**metadata, status=status,plan=plan,cost_upper=str(cost) if cost is not None else None,
        cost_lower=str(cost) if complete and cost is not None else ('0' if not complete else None),
        optimality_verified=complete,full_counts_failure_witness=full_failure,
        all_histograms_impossible_claimed=False,states_evaluated=visited,elapsed_seconds=monotonic()-start)
