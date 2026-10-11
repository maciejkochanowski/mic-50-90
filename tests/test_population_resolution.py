"""Independent partition enumeration and population precision semantics."""
from fractions import Fraction
from itertools import combinations

import pytest

from mic_50_90.model import MICPanel
from mic_50_90.empirical import EmpiricalProblem


def partitions(k):
    for size in range(k):
        for cuts in combinations(range(1, k), size):
            yield (0, *cuts, k)


def test_two_graphs_against_all_partitions():
    from mic_50_90.population_precision import maximum_population_partition
    panel = MICPanel.from_dict({'levels': [1, 2, 4, 8]})
    for target in [0, 10, 30, 100]:
        bounds = []
        for a in range(5):
            for b in range(a+1, 6):
                width = 0 if (a, b) == (0, 5) else ((a*3+b*7) % 40)/100
                bounds.append(dict(start_index=a, stop_index=b, lower=0., upper=width,
                                   inner_lower=0., inner_upper=width/2))
        pop = dict(interval_bounds=bounds, confidence_level=.95)
        result = maximum_population_partition(pop, panel, precision_pp=target, required_cuts=[2])
        lookup = {(r['start_index'], r['stop_index']): r for r in bounds}
        def allowed(a, b, inner):
            r = lookup[a, b]
            width = Fraction(r['inner_upper' if inner else 'upper'])-Fraction(r['inner_lower' if inner else 'lower'])
            return 100*width <= target
        for inner, key in [(False, 'guaranteed_number_of_bins'), (True, 'possible_number_of_bins')]:
            valid = [p for p in partitions(5) if 2 in p and all(
                allowed(a,b,inner) and allowed(0,b,inner) for a,b in zip(p,p[1:]))]
            assert result[key] == max((len(p)-1 for p in valid), default=0)


def test_existing_method_exports_all_interval_bounds():
    from mic_50_90.joint_population import population_distribution
    panel = MICPanel.from_dict({'levels': [1,2,4]})
    problem = EmpiricalProblem(n=5, panel=panel, quantiles=[], count_intervals=[([0,1,1,0],1,2)])
    for method in ['bonferroni','joint-exact']:
        pop = population_distribution({'one': problem}, method=method,
            include_intervals=True, time_limit_seconds=.01)
        assert len(pop['interval_bounds']) == 10
        for row in pop['interval_bounds']:
            assert 0 <= row['lower'] <= row['upper'] <= 1
            if row['inner_lower'] is not None:
                assert row['lower'] <= row['inner_lower'] <= row['inner_upper'] <= row['upper']


def test_population_target_requires_sampling_acknowledgement():
    from mic_50_90.distribution_workflow import analyse_distribution
    raw = dict(n=20, unit='mg/L', panel={'levels':[1,2]}, additional_counts=[
        dict(threshold=1,count=8,n=20,unit='mg/L')])
    result = analyse_distribution(raw, population_precision_pp=10)
    assert result['population_resolution']['status'] == 'unavailable'
    assert 'iid' in result['population_resolution']['reason']
    raw['iid'] = True
    result = analyse_distribution(raw, population_precision_pp=100)
    assert result['population_resolution']['maximum_number_verified']
    assert result['population_resolution']['guaranteed_number_of_bins'] == 3


def test_no_inner_witness_does_not_prove_impossibility():
    from mic_50_90.population_precision import maximum_population_partition
    panel = MICPanel.from_dict({'levels':[1,2], 'right_censored':False})
    rows = [dict(start_index=a,stop_index=b,lower=0,upper=1,inner_lower=None,inner_upper=None)
            for a,b in [(0,1),(1,2)]]
    rows.append(dict(start_index=0,stop_index=2,lower=1,upper=1,inner_lower=1,inner_upper=1))
    result = maximum_population_partition(dict(interval_bounds=rows,confidence_level=.95),panel,
        precision_pp=10,required_cuts=[1])
    assert result['status'] == 'numerically_unresolved'
    assert result['guaranteed_number_of_bins'] == 0
    assert result['possible_number_of_bins'] == 2


def test_outward_cp_rounding_cannot_certify_impossibility_at_exact_target():
    from mic_50_90.joint_population import population_distribution
    from mic_50_90.population_precision import maximum_population_partition
    from mic_50_90.population_acquisition import plan_population_precision
    panel = MICPanel.from_dict({'levels':[1,2], 'right_censored':False})
    problems = {'p': EmpiricalProblem(n=1,panel=panel,quantiles=[],
        count_intervals=[([1,0],1,1)])}
    pop = population_distribution(problems,confidence_level=.5,include_intervals=True)
    # Independent closed form: CP [alpha/2, 1] = [.25, 1].
    row = pop['interval_bounds'][0]
    assert row['inner_lower'] is None or row['inner_lower'] >= .25
    result = maximum_population_partition(pop,panel,precision_pp=75,required_cuts=[1])
    assert result['possible_number_of_bins'] == 2
    assert result['status'] != 'no_partition'
    plan = plan_population_precision(problems,confidence_level=.5,precision_pp=75,
        required_cuts=[1],time_limit_seconds=1)
    assert plan['full_counts_failure_witness'] is None
    assert plan['status'] != 'no_guaranteed_plan'


def test_saved_inner_witnesses_are_not_reused_after_a_truthful_count():
    from mic_50_90.joint_population import population_distribution, update_population_distribution
    panel=MICPanel.from_dict({'levels':[1,2],'right_censored':False})
    old={'p':EmpiricalProblem(n=20,panel=panel,quantiles=[])}
    previous=population_distribution(old,include_intervals=True,confidence_level=.5)
    new={'p':old['p'].with_count_interval([1,0],10,10)}
    updated=update_population_distribution(old,new,previous,include_intervals=True)
    first=updated['interval_bounds'][0]
    assert first['inner_lower']>0 and first['inner_upper']<1
    assert first['lower']<=first['inner_lower']<=first['inner_upper']<=first['upper']
