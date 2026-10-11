from itertools import product
import pytest
from mic_50_90.analysis import analyse_spec
from mic_50_90.empirical import EmpiricalProblem
from mic_50_90.model import MICPanel, QuantileSummary
from mic_50_90.utility import rank_robust_tail_count_questions


def test_large_canonical_search_completes_within_a_useful_budget():
    result=analyse_spec({"n":10000,"panel":{"levels":[1,2,4,8,16],
                            "left_censored":False,"right_censored":False},
                        "summaries":{"quantiles":[{"probability":.5,"category":"2"},
                                                   {"probability":.9,"category":"16"}]},
                        "thresholds":[2,8],"question_utility":{"time_limit_seconds":5}})
    assert result["one_question_recovery"]["search_complete"]
    assert result["one_question_recovery"]["best_question"]["minimax_width_reduction"] == pytest.approx(.3999)


@pytest.mark.parametrize("with_range",[False,True])
def test_union_question_scores_match_independent_composition_oracle(with_range):
    panel=MICPanel.from_twofold_levels([1,2,4,8,16],left_censored=False,right_censored=False)
    problems={name:EmpiricalProblem(n=6,panel=panel,
                quantiles=(QuantileSummary(.5,a,1,"2"),QuantileSummary(.9,b,4,"16")),
                minimum_index=0 if with_range else None,maximum_index=4 if with_range else None)
              for name,a,b in [("a",3,5),("b",4,6)]}
    hist=[]
    for a,b,c,d in product(range(7),repeat=4):
        e=6-a-b-c-d
        if e<0 or (with_range and (a<1 or e<1)):continue
        if (a<3<=a+b and a+b+c+d<5) or (a<4<=a+b and a+b+c+d<6):
            hist.append((a,b,c,d,e))
    def width(rows):
        return sum(max(sum(h[j+1:]) for h in rows)-min(sum(h[j+1:]) for h in rows)
                   for j in (1,3))/6
    scores=rank_robust_tail_count_questions(problems=problems,
                   target_objectives=[panel.panel_tail(2),panel.panel_tail(8)])
    baseline=width(hist)
    for score in scores:
        answers={sum(h[score.cut_index+1:]) for h in hist}
        residual=max(width([h for h in hist if sum(h[score.cut_index+1:])==answer]) for answer in answers)
        assert score.feasible_answers_evaluated==len(answers)
        assert score.baseline_total_width==pytest.approx(baseline)
        assert score.worst_case_residual_width==pytest.approx(residual)
        assert score.minimax_width_reduction==pytest.approx(baseline-residual)
