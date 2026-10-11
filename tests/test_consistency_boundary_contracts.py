"""Reject malformed count and target inputs without changing their meaning."""
import numpy as np
import pytest
from mic_50_90.empirical import EmpiricalProblem, closed_form_tail_counts
from mic_50_90.model import MICPanel, QuantileSummary
from mic_50_90.population import PopulationMLE, profile_likelihood
from mic_50_90.conformal import calibrate_wasserstein_manifest


def problem():
    panel=MICPanel.from_twofold_levels([1,2],left_censored=False,right_censored=False)
    return EmpiricalProblem(n=3,panel=panel,quantiles=[])


@pytest.mark.parametrize('count',[1.9,True])
def test_added_count_not_truncated(count):
    with pytest.raises(ValueError):
        problem().with_equality(np.array([0.,1.]),count)


@pytest.mark.parametrize('count',[np.nan,np.inf])
def test_nonfinite_equality_not_ignored(count):
    p=problem()
    with pytest.raises(ValueError):
        EmpiricalProblem(n=3,panel=p.panel,quantiles=[],equalities=[(np.array([0.,1.]),count)])


def test_weighted_objective_not_rounded_into_count():
    with pytest.raises(ValueError, match='finite integers'):
        problem().bounds(np.array([0.,.5]))


@pytest.mark.parametrize('objective', [np.array([0.,np.nan]),np.array([0.,np.inf]),
                                    np.array([[0.,1.]]),np.array([1.])])
def test_count_objective_shape_and_finiteness(objective):
    with pytest.raises(ValueError, match='finite integers'):
        problem().bounds(objective)


@pytest.mark.parametrize('coefficients',[np.array([0.,np.nan]),np.array([[0.,1.]])])
def test_equality_coefficient_shape_and_finiteness(coefficients):
    with pytest.raises(ValueError, match='coefficients'):
        problem().with_equality(coefficients,1)


def test_analytic_tail_not_truncated():
    with pytest.raises(ValueError):
        closed_form_tail_counts(n=3,tail=np.array([0.,.9]),quantiles=[],minimum_index=None,maximum_index=None)


@pytest.mark.parametrize('tail',[[np.nan,np.nan],[.4,.4]])
def test_profile_rejects_uninterpretable_target(tail):
    p=problem()
    mle=PopulationMLE((.5,.5),-1.,True,'independent fixture',1)
    quantiles=(QuantileSummary(.5,1,0,p.panel.labels[0],'explicit'),)
    with pytest.raises(ValueError):
        profile_likelihood(mle=mle,tail=np.array(tail),n=3,quantiles=quantiles,
                           minimum_index=None,maximum_index=None)


@pytest.mark.parametrize('size',[11.9,True,np.nan])
def test_profile_grid_size_is_an_exact_integer(size):
    p=problem()
    mle=PopulationMLE((.5,.5),-1.,True,'independent fixture',1)
    with pytest.raises(ValueError):
        profile_likelihood(mle=mle,tail=np.array([0.,0.]),n=3,
            quantiles=[QuantileSummary(.5,1,0,p.panel.labels[0],'explicit')],
            minimum_index=None,maximum_index=None,grid_size=size)


@pytest.mark.parametrize('tail',[np.array(1.),np.array([[0.,1.]]),np.array([0.,1.,1.])])
def test_profile_tail_shape_matches_mle(tail):
    p=problem()
    with pytest.raises(ValueError):
        profile_likelihood(mle=PopulationMLE((.5,.5),-1.,True,'fixture',1),
            tail=tail,n=3,quantiles=[QuantileSummary(.5,1,0,p.panel.labels[0],'explicit')],
            minimum_index=None,maximum_index=None)


def test_failed_mle_cannot_produce_fixed_profile_result():
    p=problem()
    with pytest.raises(ValueError):
        profile_likelihood(mle=PopulationMLE((.5,.5),-1.,False,'failed',1),
            tail=np.array([0.,0.]),n=3,quantiles=[QuantileSummary(.5,1,0,p.panel.labels[0],'explicit')],
            minimum_index=None,maximum_index=None)


def test_new_calibration_manifest_requires_an_explicit_contract():
    with pytest.raises(ValueError,match='contract'):
        calibrate_wasserstein_manifest(group_scores=[0.]*9,group_units=[str(i) for i in range(9)],
            alpha=.8,calibrate_on='units',grouping={'purpose':'test'},source='fixture',data_hashes={'input':'fixture'})


def test_integral_weighted_objective_and_fractional_constraint_coefficients_remain_supported():
    p=problem()
    fixed=EmpiricalProblem(n=p.n,panel=p.panel,quantiles=[],equalities=[(np.array([0.,.5]),1)])
    lo,hi=fixed.bounds(np.array([-1.,2.]))
    assert lo.histogram == hi.histogram == (1,2)
    assert lo.count == hi.count == 3


def test_calibration_ties_do_not_raise_the_prespecified_guarantee():
    from test_release_contract import contract
    from mic_50_90.conformal import validate_calibration_manifest

    manifest = calibrate_wasserstein_manifest(
        group_scores=[0.] * 9, group_units=[str(i) for i in range(9)],
        alpha=.8, calibrate_on='units', grouping={'purpose': 'test'},
        source='fixture', data_hashes={'input': 'fixture'},
        calibration_contract=contract(),
    ).as_dict()
    validate_calibration_manifest(manifest)
    assert manifest['rank'] == 2
    assert manifest['confidence_level'] == .2
    assert manifest['attained_level'] == .2
    assert manifest['attained_level_median_cohort'] is None
