"""Small trees have an independent histogram-state oracle."""
import pytest

from mic_50_90.empirical import EmpiricalProblem
from mic_50_90.model import MICPanel


def problem():
    panel = MICPanel.from_dict({'levels':[1,2], 'right_censored':False})
    return {'primary': EmpiricalProblem(n=2,panel=panel,quantiles=[])}


def test_complete_tree_matches_three_possible_histograms():
    from mic_50_90.population_acquisition import plan_population_precision
    # At 50% confidence, all n=2 complete-count binomial intervals are narrower
    # than 90pp; without counts the compatible region is the whole simplex.
    result = plan_population_precision(problem(), precision_pp=90, confidence_level=.5,
        queries=[dict(start_index=0,stop_index=1,cost='3')], time_limit_seconds=10)
    assert result['status'] == 'achievable_with_counts'
    assert result['optimality_verified']
    assert result['cost_lower'] == result['cost_upper'] == '3'
    assert set(result['plan']['answers']) == {'0','1','2'}
    assert all(child['goal_reached'] for child in result['plan']['answers'].values())


def test_full_counts_can_fail_without_claiming_every_histogram_fails():
    from mic_50_90.population_acquisition import plan_population_precision
    result = plan_population_precision(problem(),precision_pp=1,confidence_level=.95,time_limit_seconds=10)
    assert result['status'] == 'no_guaranteed_plan'
    assert result['full_counts_failure_witness'] is not None
    assert not result['all_histograms_impossible_claimed']


def test_timeout_is_not_impossibility():
    from mic_50_90.population_acquisition import plan_population_precision
    result = plan_population_precision(problem(),precision_pp=1,time_limit_seconds=0)
    assert result['status'] == 'numerically_unresolved'
    assert not result['optimality_verified']
    assert result['full_counts_failure_witness'] is None


def test_unavailable_queries_do_not_become_free_queries():
    from mic_50_90.population_acquisition import plan_population_precision
    result = plan_population_precision(problem(),precision_pp=90,confidence_level=.5,queries=[])
    assert result['status'] == 'no_guaranteed_plan'
    assert result['plan'] is None


@pytest.mark.parametrize('cost',['0','-1','nan'])
def test_invalid_costs_refused(cost):
    from mic_50_90.population_acquisition import plan_population_precision
    with pytest.raises(ValueError):
        plan_population_precision(problem(),precision_pp=90,queries=[dict(start_index=0,stop_index=1,cost=cost)])


@pytest.mark.parametrize('target',[65,80,90])
def test_cost_against_independent_histogram_tree(target):
    from functools import lru_cache
    from math import inf
    from scipy.stats import beta
    from mic_50_90.population_acquisition import plan_population_precision
    panel = MICPanel.from_dict({'levels':[1,2]})
    n=3
    hist=tuple((a,b,n-a-b) for a in range(n+1) for b in range(n-a+1))
    queries=[(0,1,3),(1,2,1),(0,2,2)]
    def sufficient(state):
        lows=[0]; highs=[0]
        for b in [1,2]:
            counts=[sum(h[:b]) for h in state]
            low,high=min(counts),max(counts)
            lows.append(0 if low==0 else beta.ppf(.125,low,n-low+1))
            highs.append(1 if high==n else beta.ppf(.875,high+1,n-high))
        lows.append(1);highs.append(1)
        return all(100*(highs[b]-lows[b])<=target and
            100*(min(1,highs[b]-lows[b-1])-max(0,lows[b]-highs[b-1]))<=target for b in [1,2,3])
    @lru_cache(None)
    def oracle(state):
        if sufficient(state):return 0
        costs=[]
        for a,b,c in queries:
            answers={sum(h[a:b]) for h in state}
            if len(answers)>1:
                costs.append(c+max(oracle(tuple(h for h in state if sum(h[a:b])==x)) for x in answers))
        return min(costs,default=inf)
    expected=oracle(hist)
    result=plan_population_precision({'p':EmpiricalProblem(n=n,panel=panel,quantiles=[])},
        confidence_level=.5,precision_pp=target,time_limit_seconds=20,
        queries=[dict(start_index=a,stop_index=b,cost=c) for a,b,c in queries])
    assert result['optimality_verified']
    if expected==inf:
        assert result['status']=='no_guaranteed_plan'
    else:
        assert float(result['cost_upper'])==expected


def test_workflow_exports_plan_and_next_count(tmp_path):
    import json
    from mic_50_90.cli import main
    raw=dict(n=2,unit='mg/L',panel=problem()['primary'].panel.as_dict(),iid=True,confidence_level=.5,
        additional_counts=[dict(threshold=1,count_min=0,count_max=2,n=2,unit='mg/L')])
    source=tmp_path/'input.json';source.write_text(json.dumps(raw))
    assert main(['distribution',str(source),'--population-precision-pp','90','--population-count-plan',
        '--output-dir',str(tmp_path/'out')])==0
    result=json.loads((tmp_path/'out/results.json').read_text())['cohorts'][0]
    assert result['population_count_plan']['status']=='achievable_with_counts'
    assert 'Next count to request' in (tmp_path/'out/report.html').read_text(encoding='utf-8')
