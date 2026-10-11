"""Human-readable acquisition plans; complete policies remain in JSON."""

from __future__ import annotations

import html
from fractions import Fraction


def _criterion_percent(criterion):
    """Display the exact decision boundary, without rounding it into another question."""
    value = criterion.get('decision_fraction_text', criterion.get('decision_fraction'))
    if value is None:
        return 'not available'
    percent = 100 * Fraction(str(value))
    denominator = percent.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        return f'{percent.numerator}/{percent.denominator}%'
    places = max(twos, fives)
    scaled = percent.numerator * 2**(places-twos) * 5**(places-fives)
    if not places:
        return f'{scaled}%'
    digits = str(scaled).zfill(places+1)
    return digits[:-places] + '.' + digits[-places:].rstrip('0') + '%'


def _amount(value, noun):
    text = _text(value)
    return f'{text} {noun if text == "1" else noun + "s"}'


def _text(value):
    if value is None:
        return "not available"
    return html.escape(f"{value:g}" if isinstance(value, float) else str(value))


def _table(headers, rows):
    return ('<div class="table-scroll"><table><thead><tr>'
            + ''.join('<th>' + _text(value) + '</th>' for value in headers)
            + '</tr></thead><tbody>'
            + ''.join('<tr>' + ''.join('<td>' + value + '</td>' for value in row) + '</tr>' for row in rows)
            + '</tbody></table></div>')


def _question(question):
    return ("Count recorded MIC values strictly above " + _text(question.get("threshold"))
            + " " + _text(question.get("unit")) + ". Cost in acquisition units: "
            + _text(question.get("cost_exact", question.get("cost"))) + ".")


def _decisions(statuses):
    return "; ".join("criterion " + str(index) + ": " + _text(status)
                     for index, status in enumerate(statuses, 1))


def render_decision_plan(result):
    """Explain the present action without implying population stopping rules."""
    if result.get("acquisition_plan"):
        return render_acquisition_plan(result["acquisition_plan"])
    plan = result.get("decision_plan")
    if not plan:
        return ""
    parts = ['<h2>Counts to resolve your criteria</h2>',
             '<p>This plan concerns recorded values in the original cohort. Each selected sample criterion '
             'must be resolved separately. Population and calibrated results retain their own guarantees.</p>']
    if plan.get("status") == "unavailable" or plan.get("available") is False:
        parts.append('<p class="warning">' + _text(plan.get("reason", "Decision planning unavailable")) + '</p>')
        return ''.join(parts)

    rows = []
    for index, criterion in enumerate(plan.get("criteria", []), 1):
        question = ('Recorded fraction above ' + _text(criterion.get("threshold")) + ' '
                    + _text(criterion.get("unit")) + ' ' + _text(criterion.get("decision_operator"))
                    + ' ' + _text(criterion.get("decision_fraction_text", criterion.get("decision_fraction"))))
        rows.append([str(index), question, _text(criterion.get("initial_status"))])
    if rows:
        parts.append(_table(["Criterion", "Exact fraction criterion (0.05 means 5%)", "Current sample status"], rows))

    status = plan.get("status")
    cost = plan.get("worst_case_cost_exact", plan.get("worst_case_cost"))
    if status == "already_resolved":
        parts.append('<p><strong>No further counts are needed. Stop: every selected sample criterion is resolved.</strong></p>')
    elif status == "optimal" and plan.get("optimality_verified"):
        parts.append('<p><strong>Minimum worst-case acquisition cost: ' + _text(cost)
                     + '.</strong> This covers every feasible answer under the declared inputs.</p>')
    elif status == "impossible":
        parts.append('<p class="warning"><strong>The allowed counts cannot resolve every criterion.</strong> '
                     'The compatible histograms below give the same answers at every allowed cut but different '
                     'decisions. These are mathematical examples, not reconstructed observations.</p>')
    else:
        parts.append('<p class="warning"><strong>Search incomplete; a minimum is not established.</strong></p>')
        if plan.get("cost_interpretation") == "verified_upper_bound" and cost is not None:
            parts.append('<p>The saved feasible strategy gives a verified upper bound of ' + _text(cost)
                         + ' acquisition units. It may use more information than necessary.</p>')
        else:
            parts.append('<p>No complete strategy has been verified; no next-count recommendation is made.</p>')
    if plan.get("reason"):
        parts.append('<p>' + _text(plan["reason"]) + '</p>')
    if plan.get("fixed_plan_cost") is not None:
        label = 'Minimum fixed-plan cost' if plan.get("fixed_plan_optimality_verified") else 'Fixed-plan baseline cost'
        parts.append('<p>' + label + ': ' + _text(plan.get("fixed_plan_cost_exact", plan["fixed_plan_cost"])) + '.</p>')

    next_question = plan.get("next_question")
    if next_question and status not in {"already_resolved", "impossible"}:
        parts.append('<p><strong>Next request: ' + _question(next_question) + '</strong></p>')
        parts.append('<p>Use the same original denominator, n=' + _text(plan.get("sample_size"))
                     + '. Obtain an exact aggregate count from the existing records, add it to your additional-counts '
                     'CSV and rerun batch with --additional-counts. Retain all previous answers.</p>')
    if status not in {"impossible", "already_resolved"}:
        parts.append('<p><strong>Stop when every selected sample criterion is supported or contradicted.</strong> '
                     'Recalculate the remaining plan after each answer. This is not a stopping rule for population inference.</p>')
    parts.append('<p>Costs refer to information still to be acquired. A cost unit means one count request only when '
                 'all declared query costs equal one; it is not a measured amount of laboratory work.</p>')

    witness = plan.get("impossibility_witness")
    if witness:
        rows = [[str(index), _text(', '.join(str(count) for count in state["histogram"])),
                 _decisions(state.get("decisions", []))]
                for index, state in enumerate(witness.get("states", []), 1)]
        parts.append(_table(["Compatible example", "Category counts in panel order", "Sample decisions"], rows))

    policy = plan.get("policy") or {}
    if policy.get("kind") == "adaptive_tree":
        nodes = policy.get("nodes", {})
        root = nodes.get(policy.get("root"), {})
        branches = root.get("branches", [])
        rows = []
        for branch in branches[:30]:
            child = nodes.get(branch.get("next_node"), {})
            answer = _text(branch.get("count_min")) + ' to ' + _text(branch.get("count_max"))
            action = _question(child["question"]) if child.get("question") else 'Stop: ' + _decisions(child.get("decisions", []))
            rows.append([answer, action])
        if rows:
            parts.append('<details><summary>Possible answers to the next request</summary>'
                         + _table(["Exact integer count returned", "Next action"], rows))
            if len(branches) > len(rows):
                parts.append('<p>First 30 answer ranges shown. The complete policy is retained in the JSON output.</p>')
            parts.append('</details>')
    elif policy.get("kind") == "fixed_order" and policy.get("questions"):
        parts.append('<details><summary>Verified fallback request order</summary><ol>'
                     + ''.join('<li>' + _question(question) + '</li>' for question in policy["questions"])
                     + '</ol><p>Stop early when every sample criterion is resolved.</p></details>')
    parts.append('<p>The complete criteria, policy, search status and any impossibility witnesses are retained in the JSON output.</p>')
    return ''.join(parts)


def render_acquisition_plan(plan):
    """Translate the saved policy into requests for existing laboratory records."""
    parts = ['<h2>Which additional counts do you need?</h2>',
             '<p>These are counts from existing laboratory records, not new susceptibility tests. '
             'Keep the original sample of ' + _text(plan.get('sample_size')) + ' isolates.</p>']
    labels = dict(supported='Yes', contradicted='No', undetermined='More information needed', unavailable='Unavailable')
    rows = []
    for item in plan.get('criteria',[]):
        rows.append([_text(item.get('threshold'))+' '+_text(item.get('unit')),
                     _text(item.get('decision_operator'))+' '+_text(_criterion_percent(item)),
                     labels.get(item.get('initial_status'),'Unavailable')])
    if rows:
        parts.append(_table(['Recorded MIC above','Is the sample percentage','Answer now'],rows))
    if plan.get('status') == 'already_resolved':
        parts.append('<p><strong>No additional counts are needed.</strong> All selected sample questions are answered.</p>')
    elif plan.get('status') in {'impossible','unavailable'}:
        parts.append('<p class="warning">'+_text(plan.get('reason'))+'</p>')
    elif plan.get('policy') is None:
        parts.append('<p class="warning">No sufficient request has been verified. '
                     'The search is incomplete. No upper cost bound or complete request plan has been verified; '
                     'no upper bound on request rounds is available.</p>')
        if plan.get('cost_lower_bound_exact') is not None:
            parts.append('<p>Verified lower bound: '+_amount(plan['cost_lower_bound_exact'], 'declared cost unit')
                         +'. Every sufficient strategy must cost at least this much '
                         'in its worst case, but no strategy achieving this bound has been verified.</p>')
    else:
        parts.append('<p><strong>Remaining work:</strong> at most '+_amount(plan.get('worst_case_cost_exact'), 'declared cost unit')
                     +'; at most '+_amount(plan.get('maximum_rounds'), 'request round')+' and '
                     +_amount(plan.get('maximum_counts'), 'count')+'. These are separate worst-case bounds.</p>')
        if plan.get('optimality_verified'):
            parts.append('<p>No permitted strategy has a smaller worst-case cost under these inputs.</p>')
        else:
            parts.append('<p class="warning">Search incomplete. A cheapest strategy has not been established. '
                         +_text(plan.get('reason'))+'</p>')
        if plan.get('cost_lower_bound_exact') is not None:
            parts.append('<p>Verified range for the smallest worst-case cost: '
                         +_text(plan['cost_lower_bound_exact'])+' to '+_text(plan.get('cost_upper_bound_exact'))
                         +' declared units. The lower end is unavoidable; the upper end is achieved by the saved plan.</p>')
            if plan.get('cost_gap_exact') == '0' and not plan.get('optimality_verified'):
                parts.append('<p>The cost is established because these bounds coincide. '
                             'The unfinished search has not checked tie-breaking by rounds and counts.</p>')
        parts.append('<p>Requesting the saved sufficient set without choosing later questions costs '
                     +_text(plan.get('fixed_plan_cost_exact'))+' units.</p>')
        comparison = plan.get('sequential_comparison')
        if comparison:
            label = 'Confirmed smallest worst-case cost' if comparison.get('optimality_verified') else 'Sufficient cost bound; search incomplete'
            parts.append('<p>Requesting only one count per round: '+_text(comparison.get('worst_case_cost_exact'))
                         +' units. '+label+'.</p>')
        questions = plan.get('next_questions',[])
        if questions:
            parts.append('<h3>Request together</h3><ul>'+''.join(
                '<li>Number of isolates with recorded MIC strictly above '+_text(q['threshold'])+' '
                +_text(q['unit'])+'.</li>' for q in questions)+'</ul>')
            parts.append('<p>Fill in requested_counts.csv, retain all previous answers, and rerun with '
                         '--additional-counts pointing to the completed file. Use a different output directory '
                         'to preserve your completed input.</p>')
    parts.append('<p>One round costs '+_text(plan.get('round_cost_exact'))
                 +' units plus the stated costs of its counts. These are user-declared costs, not measured staff time. '
                 'A percentage above an arbitrary concentration is not automatically a resistance percentage. '
                 'Population and calibrated results have separate assumptions and guarantees.</p>')
    return ''.join(parts)
