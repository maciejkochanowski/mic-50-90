"""Cheap option validation shared by the form and distribution workflow."""
from .validation import decimal_number, exact_integer


def option_issues(options, *, categories=None):
    issues = {}
    for key in ('precision_pp', 'population_precision_pp', 'population_tolerance_pp',
                'population_time_limit', 'population_planning_time_limit'):
        value = options.get(key)
        if value is None:
            continue
        try:
            number = decimal_number(value, key)
            if number < 0 or (key.endswith('_pp') and number > 100):
                raise ValueError(key + ' must lie in [0,100]' if key.endswith('_pp') else key + ' must be nonnegative')
            if key == 'population_tolerance_pp' and number == 0:
                raise ValueError('population_tolerance_pp must be positive')
            if not float(number) < float('inf'):
                raise ValueError(key + ' must be representable as a finite number')
        except (ValueError, OverflowError) as exc:
            issues[key] = str(exc)
    if options.get('population_minimum_bins') is not None:
        try:
            n = exact_integer(options['population_minimum_bins'], 'population_minimum_bins', 1)
            if categories is not None and n > categories:
                raise ValueError('population_minimum_bins exceeds the number of panel categories')
        except ValueError as exc:
            issues['population_minimum_bins'] = str(exc)
    if 'population_count_plan' in options and not isinstance(options['population_count_plan'], bool):
        issues['population_count_plan'] = 'population_count_plan must be true or false'
    if options.get('population_method', 'bonferroni') not in ('bonferroni', 'joint-exact', 'range-calibrated', 'range-hunter'):
        issues['population_method'] = 'Choose bonferroni, joint-exact, range-calibrated or range-hunter'
    return issues
