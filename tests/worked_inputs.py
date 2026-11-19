"""Small source-labelled inputs shared by the tests.

Each entry gives the analysis mode and the input configuration of one worked case: a controlled
summary of 20 isolates, a reporting audit of the same 20 isolates, the published Madrid counts of
7133 pneumococci and the 276 canine E. coli amikacin results of the laboratory example.
"""


def worked_inputs():
    summary = {"cohort_id": "controlled-20", "unit": "mg/L", "n": 20, "panel": {"levels": [1, 2]},
        "summaries": {"quantiles": [{"probability": .5, "category": "<=1", "convention": "ceiling"},
                                     {"probability": .9, "category": "2", "convention": "ceiling"}]},
        "iid": False, "confidence_level": .95}
    published = {"cohort_id": "Antibiotics-2023-12-289-coarse-counts", "n": 7133, "unit": "mg/L",
        "panel": {"categories": [
            {"label": "<=0.06", "lower_bound": None, "upper_bound": .06, "lower_closed": False, "upper_closed": True, "panel_value": .06},
            {"label": "(0.06,2]", "lower_bound": .06, "upper_bound": 2, "lower_closed": False, "upper_closed": True, "panel_value": 2},
            {"label": ">2", "lower_bound": 2, "upper_bound": None, "lower_closed": False, "upper_closed": False, "panel_value": 4}]},
        "additional_counts": [{"threshold": c, "count": k, "n": 7133, "unit": "mg/L",
            "source": "https://doi.org/10.3390/antibiotics12020289; verified published category counts"}
            for c, k in ((.06, 1726), (2, 143))], "iid": False, "confidence_level": .95}
    published.update(organism="Streptococcus pneumoniae", antimicrobial="Penicillin",
        source_doi="10.3390/antibiotics12020289", source_location="Table 1 total row, 2007–2021; concentration definitions in Methods",
        source="de Miguel et al. (2023), Madrid invasive isolates; https://doi.org/10.3390/antibiotics12020289",
        panel_basis="Broad groups defined by the published count thresholds; not a fine MIC histogram",
        rank_basis="Counts-only analysis; no quantile convention assumed", explain_counts=True,
        targets=[{"threshold": 2, "unit": "mg/L", "decision_operator": "<", "decision_fraction": "0.05"}],
        question_note="The 5% criterion is an illustrative user question, not a clinical breakpoint or a study endpoint.")
    laboratory = {"cohort_id": "FDA-NAHLN-2024-dogs-amikacin-276", "n": 276, "unit": "mg/L",
        "panel": {"levels": [4, 8, 16, 32]}, "iid": False, "confidence_level": .95,
        "organism": "Escherichia coli", "antimicrobial": "Amikacin",
        "source": "FDA animal-pathogen AMR data, NAHLN 2024; dogs, other tissues/body sites",
        "source_location": "https://www.fda.gov/animal-veterinary/national-antimicrobial-resistance-monitoring-system/2017-2024-animal-pathogen-amr-data",
        "rank_basis": "Ceiling-rank summaries generated from the published category counts for this reporting demonstration"}
    return [
        {"id": "summary20", "label": "Controlled example: summaries for 20 isolates", "payload": {
            "mode": "distribution", "config": summary, "options": {}}},
        {"id": "counts20", "label": "Controlled example: reporting audit for 20 isolates", "payload": {
            "mode": "reporting-audit", "config": {k: v for k, v in summary.items() if k != "summaries"},
            "rank_convention": "ceiling", "histogram": [{"category": label, "count": count} for label, count in (("<=1", 8), ("2", 10), (">2", 2))],
            "targets": [{"threshold": 1, "unit": "mg/L", "decision_operator": "<", "decision_fraction": "0.7"}],
            "options": {"reporting_plan": True}}},
        {"id": "published7133", "label": "Published counts: 7,133 isolates", "payload": {
            "mode": "distribution", "config": published, "options": {}}},
        {"id": "laboratory276", "label": "Real laboratory counts: 276 isolates, four questions", "payload": {
            "mode": "reporting-audit", "config": laboratory, "rank_convention": "ceiling",
            "histogram": [{"category": label, "count": count} for label, count in
                          (("<=4", 268), ("8", 7), ("16", 0), ("32", 0), (">32", 1))],
            "targets": [{"threshold": level, "unit": "mg/L", "decision_operator": "<", "decision_fraction": "0.05"}
                        for level in (4, 8, 16, 32)], "options": {"reporting_plan": True}}},
    ]
