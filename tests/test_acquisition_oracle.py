"""Independent finite histograms, without production prefix/state helpers."""
from fractions import Fraction
from functools import lru_cache
from itertools import combinations
import operator

from mic_50_90 import plan_acquisition
from test_decision_planning import specification, criteria


def histograms(n, k):
    if k == 1:
        yield (n,)
    else:
        for first in range(n+1):
            for rest in histograms(n-first,k-1):
                yield (first,)+rest


def compatible(raw, h):
    values = [str(2**j) for j,c in enumerate(h) for _ in range(c)]
    summaries = [raw['summaries']]+[r['summaries'] for r in raw.get('reporting_envelope',{}).get('variants',[])]
    return any(all(values[q['rank']-1] == q['category'] for q in s['quantiles'])
               and ('minimum' not in s or values[0] == s['minimum'])
               and ('maximum' not in s or values[-1] == s['maximum']) for s in summaries)


def oracle(raw, criteria_rows, queries, rho):
    hs = tuple(h for h in histograms(raw['n'],len(raw['panel']['levels'])) if compatible(raw,h))
    ops = {'<':operator.lt,'<=':operator.le,'>':operator.gt,'>=':operator.ge}
    def answer(h, threshold):
        return sum(c for j,c in enumerate(h) if 2**j > threshold)
    truths = [tuple(ops[c['decision_operator']](Fraction(answer(h,c['threshold']),raw['n']),
                    Fraction(str(c['decision_fraction']))) for c in criteria_rows) for h in hs]
    @lru_cache(None)
    def solve(ids):
        if len({truths[i] for i in ids}) == 1:
            return Fraction(0)
        active = [q for q in range(len(queries)) if len({answer(hs[i],queries[q]['threshold']) for i in ids})>1]
        best = None
        for size in range(1,len(active)+1):
            for batch in combinations(active,size):
                groups = {}
                for i in ids:
                    key = tuple(answer(hs[i],queries[q]['threshold']) for q in batch)
                    groups.setdefault(key,[]).append(i)
                children = [solve(tuple(group)) for group in groups.values()]
                if any(c is None for c in children):
                    continue
                value = Fraction(str(rho))+sum(Fraction(str(queries[q]['cost'])) for q in batch)+max(children)
                best = value if best is None else min(best,value)
        return best
    return solve(tuple(range(len(hs)))),hs,truths


def check_tree(result, hs, truths):
    policy = result['policy']
    for histogram, truth in zip(hs,truths):
        if result['status'] == 'already_resolved':
            assert [c['initial_status']=='supported' for c in result['criteria']] == list(truth)
            continue
        node = policy['nodes'][policy['root']]
        cost, rounds, counts = Fraction(0),0,0
        while 'questions' in node:
            questions = node['questions']
            answers = [sum(c for j,c in enumerate(histogram) if 2**j>q['threshold']) for q in questions]
            branch, = [b for b in node['branches'] if all(
                lo['count_min']<=a<=lo['count_max'] for a,lo in zip(answers,b['answers']))]
            cost += Fraction(result['round_cost_exact'])+sum(Fraction(q['cost_exact']) for q in questions)
            rounds += 1
            counts += len(questions)
            node = policy['nodes'][branch['next_node']]
        assert 'undetermined' not in node['decisions']
        assert [s=='supported' for s in node['decisions']] == list(truth)
        assert cost <= Fraction(result['worst_case_cost_exact'])
        assert rounds <= result['maximum_rounds'] and counts <= result['maximum_counts']


def test_independent_exhaustive_small_samples():
    cases = 0
    for n in range(2,7):
        for first,second in combinations(range(4),2):
            raw = specification(n,4)
            raw['summaries']['quantiles'][0]['category'] = str(2**first)
            raw['summaries']['quantiles'][1]['category'] = str(2**second)
            for fractions in [('.5','.5','.5'),('.1','.5','.9')]:
                cs = [dict(c,decision_fraction=f,decision_operator=op) for c,f,op in
                      zip(criteria((1,2,4)),fractions,('<','<=','>='))]
                for prices,rho in [((1,1,1),0),((1,1,1),2),((0,0,0),1),((1,4,0),1)]:
                    qs = [dict(threshold=t,unit='mg/L',cost=p) for t,p in zip((1,2,4),prices)]
                    expected,hs,truths = oracle(raw,cs,qs,rho)
                    result = plan_acquisition(raw,cs,queries=qs,round_cost=rho)
                    assert result['optimality_verified']
                    assert Fraction(result['worst_case_cost_exact']) == expected
                    check_tree(result,hs,truths)
                    cases += 1
    assert cases == 240


def test_union_with_cheap_joint_off_target_information():
    hs = [(0,1,1,1),(0,2,1,0),(1,1,0,1),(1,0,2,0)]
    summaries=[]
    for h in hs:
        values=[str(2**j) for j,c in enumerate(h) for _ in range(c)]
        summaries.append(dict(minimum=values[0],quantiles=[
            dict(probability=.5,rank=2,category=values[1]),dict(probability=.9,rank=3,category=values[2])]))
    raw=specification(3,4)
    raw['summaries']=summaries[0]
    raw['reporting_envelope']=dict(variants=[dict(id=str(i),summaries=s) for i,s in enumerate(summaries[1:])])
    cs=criteria((2,),fraction='.5',op='<=')
    for qs in [[dict(threshold=t,unit='mg/L',cost=p) for t,p in [(1,1),(2,4),(4,1)]],
               [dict(threshold=1,unit='mg/L',cost=1)]]:
        expected,possible,truths=oracle(raw,cs,qs,2)
        result=plan_acquisition(raw,cs,queries=qs,round_cost=2)
        if expected is None:
            assert result['status']=='impossible'
        else:
            assert Fraction(result['worst_case_cost_exact'])==expected==4
            check_tree(result,possible,truths)
