"""Build the confirmation tables from the public isolate-level files (PROTOCOL.md, sections 2 and 6).

Input: the six files fetched by download_sources.py (checked by SHA-256). Output in data/benchmark/:
  cohorts.jsonl.gz   the selected confirmation cohorts, in their fixed order (complete tables)
  eligible.csv.gz    every eligible cohort with its stratum, hash rank and whether it was selected
  groups.csv.gz      every panel group with its panel or the reason it was excluded
  units.jsonl.gz     the unit tables of the six calibration datasets, with their roles
  summary.json       counts at every step and the SHA-256 of every input file
The build is deterministic; running it twice gives byte-identical tables.
"""
from __future__ import annotations

import common

import argparse
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from common import DATA, gzip_text, now, read_json, write_csv, write_json
from download_sources import DEFAULT, SOURCES, digest

OUT = DATA / 'benchmark'
NARMS = {
    'narms_retail_meats.xlsx': 'NARMS retail meats',
    'narms_haccp_1997_2005.xlsx': 'NARMS slaughter',
    'narms_haccp_2006_present.xlsx': 'NARMS slaughter',
    'narms_cecal_2013_present.xlsx': 'NARMS cecal',
    'narms_minor_species_2020_2022.xlsx': 'NARMS minor species',
}
ANIMAL = 'fda_animal_pathogen_2017_2024.xlsx'
GENUS = {'Escherichia': 'E. coli', 'E. coli': 'E. coli', 'Salmonella': 'Salmonella', 'Campylobacter': 'Campylobacter',
         'Enterococcus': 'Enterococcus', 'S. pseudintermedius': 'S. pseudintermedius', 'Klebsiella spp': 'Klebsiella'}
PER_STRATUM = 10
MIN_N, MAX_N, MIN_K, MAX_K = 20, 1000, 3, 12
TOLERANCE = 0.07
DATASETS = (  # name, source, genus
    ('dogs-ecoli', 'FDA animal pathogens', 'E. coli'),
    ('dogs-spseud', 'FDA animal pathogens', 'S. pseudintermedius'),
    ('retail-salmonella', 'NARMS retail meats', 'Salmonella'),
    ('retail-campylobacter', 'NARMS retail meats', 'Campylobacter'),
    ('retail-ecoli', 'NARMS retail meats', 'E. coli'),
    ('retail-enterococcus', 'NARMS retail meats', 'Enterococcus'),
)
UNIT_MINIMUM = 5
MIN_DRUGS = 3
MIN_UNITS = 9


def text(value):
    return '' if value is None or (isinstance(value, float) and math.isnan(value)) else str(value).strip()


def records(folder):
    """One record per isolate and drug: source, agency, host, genus, year, state, isolate, drug, sign, value."""
    import pandas as pd
    for name, source in NARMS.items():
        frame = pd.read_excel(folder / name, engine='openpyxl', dtype=object)
        year = 'YEAR' if 'YEAR' in frame.columns else 'Year'
        frame = frame[frame['GROWTH'].map(text).str.upper() == 'YES']
        drugs = [c for c in frame.columns if re.fullmatch(r'[A-Z0-9]{2,5}', str(c)) and f'{c} Sign' in frame.columns]
        keep = ['AGENCY', 'HOST_SPECIES', 'GENUS_NAME', year, 'STATE', 'ISOLATE_ID']
        for drug in drugs:
            part = frame[keep + [f'{drug} Sign', drug]].dropna(subset=[drug])
            for row in part.itertuples(index=False):
                yield (source, text(row[0]), text(row[1]), GENUS.get(text(row[2]), text(row[2])), int(row[3]), text(row[4]),
                       text(row[5]), drug, text(row[6]), row[7])
    frame = pd.read_excel(folder / ANIMAL, engine='openpyxl', dtype=object)
    for row in frame[['Agency', 'Host Species', 'Genus', 'Year', 'State', 'Sample ID', 'Drug Name', 'Sign', 'MIC']].itertuples(index=False):
        yield ('FDA animal pathogens', text(row[0]), text(row[1]), GENUS.get(text(row[2]), text(row[2])), int(row[3]), text(row[4]),
               text(row[5]), text(row[6]), text(row[7]), row[8])


def step(value):
    """Doubling step of a value, or None when it is not within TOLERANCE of a doubling dilution."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if not value > 0:
        return None
    exponent = math.log2(value)
    nearest = round(exponent)
    return nearest if abs(exponent - nearest) <= TOLERANCE else None


def panel_of(signs):
    """Panel (L, H) of a panel group from its {sign: set of steps}, or the reason it is excluded."""
    below, equal, above = signs.get('<=', set()), signs.get('=', set()), signs.get('>', set())
    if None in below | equal | above:
        return None, 'value not on the doubling-dilution scale'
    if len(below) > 1:
        return None, 'more than one <= step'
    if len(above) > 1:
        return None, 'more than one > step'
    steps = below | equal | above
    low, high = min(steps), max(steps)
    if below and min(equal, default=low) < min(below):
        return None, '= value below the <= step'
    if above and max(equal, default=high) > max(above):
        return None, '= value above the > step'
    if above:
        high = max(above)
    k = high - low + 2
    if not MIN_K <= k <= MAX_K:
        return None, f'{k} categories'
    return (low, high), None


def index(sign, e, low, high):
    if sign == '<=':
        return 0
    if sign == '>':
        return high - low + 1
    return max(0, e - low)


def unit_tables(source, agency, genus, year, drugs, panels, table):
    """State tables of one year: state -> drug -> counts, for states with enough isolates for every drug."""
    per_state = defaultdict(dict)
    for (group, host, state), items in table.items():
        if group[:4] == (source, agency, genus, year) and group[4] in drugs and state:
            low, high = panels[group]
            counts = per_state[state].setdefault(group[4], [0] * (high - low + 2))
            for sign, e, _ in items:
                counts[index(sign, e, low, high)] += 1
    return {s: v for s, v in per_state.items() if all(sum(v.get(d, [])) >= UNIT_MINIMUM for d in drugs)}


def choose(source, genus, panels, table):
    """Latest three consecutive years T < C < V with at least MIN_DRUGS drugs on one panel in all three
    years and at least MIN_UNITS states in every role; the agency with more calibration states."""
    years = sorted({g[3] for g in panels if g[0] == source and g[2] == genus}, reverse=True)
    for test in years:
        span = dict(training=test - 2, calibration=test - 1, test=test)
        best = None
        for agency in sorted({g[1] for g in panels if g[0] == source and g[2] == genus and g[3] == span['calibration']}):
            drugs = sorted(d for d in {g[4] for g in panels if g[:4] == (source, agency, genus, span['calibration'])}
                           if all(panels.get((source, agency, genus, y, d)) == panels[(source, agency, genus, span['calibration'], d)]
                                  for y in span.values()))
            if len(drugs) < MIN_DRUGS:
                continue
            roles = {role: unit_tables(source, agency, genus, y, drugs, panels, table) for role, y in span.items()}
            if min(len(v) for v in roles.values()) < MIN_UNITS:
                continue
            candidate = (len(roles['calibration']), agency, drugs, roles, span)
            if best is None or candidate[0] > best[0]:
                best = candidate
        if best:
            return best
    return None


def development_keys():
    keys = set()
    for row in read_json(DATA / 'population_cohorts.json'):
        if row['source'] == 'FDA animal pathogens':
            _, agency, year, genus, _, _, drug = row['cohort_id'].split('|')
            keys.add((agency, int(year), GENUS.get(genus, genus), drug))
    return keys


def sha(text_value):
    return hashlib.sha256(text_value.encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--sources', type=Path, default=DEFAULT, help='folder of the downloaded files (default: evaluation/sources)')
    args = parser.parse_args()
    hashes = {}
    for name, (_, expected) in SOURCES.items():
        found = digest(args.sources / name)
        if found != expected:
            raise SystemExit(f'{name}: SHA-256 {found} differs from the recorded {expected}; run download_sources.py')
        hashes[name] = found
    signs = defaultdict(lambda: defaultdict(set))   # group -> sign -> steps
    table = defaultdict(list)                       # (group, host, state) -> [(sign, step, isolate)]
    dropped = Counter()
    for source, agency, host, genus, year, state, isolate, drug, sign, value in records(args.sources):
        if sign not in ('<=', '=', '>'):
            dropped['sign ' + (sign or 'missing')] += 1
            continue
        group = (source, agency, genus, year, drug)
        e = step(value)
        signs[group][sign].add(e)
        if e is not None:
            table[(group, host, state)].append((sign, e, isolate))
    panels, group_rows = {}, []
    for group in sorted(signs):
        found, reason = panel_of(signs[group])
        if found:
            panels[group] = found
        group_rows.append(dict(source=group[0], agency=group[1], genus=group[2], year=group[3], drug=group[4],
                               low=found[0] if found else '', high=found[1] if found else '', excluded=reason or ''))
    write_csv(OUT / 'groups.csv.gz', group_rows)
    # cohorts: panel group and host, pooled over states
    pooled = defaultdict(list)
    for (group, host, state), items in table.items():
        if group in panels:
            pooled[(group, host)] += items
    development = development_keys()
    eligible = []
    for (group, host), items in sorted(pooled.items()):
        low, high = panels[group]
        counts = [0] * (high - low + 2)
        for sign, e, _ in items:
            counts[index(sign, e, low, high)] += 1
        n = sum(counts)
        source, agency, genus, year, drug = group
        reason = ''
        if not MIN_N <= n <= MAX_N:
            reason = 'n outside 20-1000'
        elif sum(c > 0 for c in counts) < 2:
            reason = 'one occupied category'
        elif source == 'FDA animal pathogens' and (agency, year, genus, drug) in development:
            reason = 'shares records with a development cohort'
        cohort_id = '|'.join([source, agency, str(year), genus, host, drug])
        eligible.append(dict(cohort_id=cohort_id, stratum='|'.join([source, host, genus]), source=source, agency=agency,
                             year=year, genus=genus, host=host, drug=drug, low=low, high=high, n=n, k=len(counts),
                             counts=counts, reason=reason, hash=sha(cohort_id)))
    chosen = []
    for stratum in sorted({r['stratum'] for r in eligible if not r['reason']}):
        members = sorted((r for r in eligible if r['stratum'] == stratum and not r['reason']), key=lambda r: r['hash'])
        for rank, r in enumerate(members, 1):
            r['rank'] = rank
            r['selected'] = rank <= PER_STRATUM
        chosen += members[:PER_STRATUM]
    chosen.sort(key=lambda r: (r['stratum'], r['rank']))
    write_csv(OUT / 'eligible.csv.gz', [{k: (json.dumps(v) if k == 'counts' else v) for k, v in r.items()} for r in eligible])
    with gzip_text(OUT / 'cohorts.jsonl.gz') as handle:
        for position, r in enumerate(chosen):
            row = {k: r[k] for k in ('cohort_id', 'stratum', 'source', 'agency', 'year', 'genus', 'host', 'drug', 'low', 'high',
                                     'n', 'k', 'counts')}
            handle.write(json.dumps(dict(position=position, **row)) + '\n')
    # calibration datasets: units are states
    unit_rows, datasets = [], {}
    for name, source, genus in DATASETS:
        best = choose(source, genus, panels, table)
        size, agency, drugs, roles, years = best if best else (0, '', [], {}, {})
        datasets[name] = dict(source=source, genus=genus, agency=agency, years=years, drugs=drugs,
                              units={role: len(v) for role, v in roles.items()},
                              level=0.95 if size >= 19 else 0.9 if size >= MIN_UNITS else None)
        for role, states in roles.items():
            for state in sorted(states):
                for drug in drugs:
                    low, high = panels[(source, agency, genus, years[role], drug)]
                    counts = states[state][drug]
                    unit_rows.append(dict(dataset=name, role=role, year=years[role], unit_id=state, drug=drug, low=low, high=high,
                                          n=sum(counts), counts=counts))
    with gzip_text(OUT / 'units.jsonl.gz') as handle:
        for r in unit_rows:
            handle.write(json.dumps(r) + '\n')
    excluded = Counter(r['excluded'] for r in group_rows if r['excluded'])
    reasons = Counter(r['reason'] for r in eligible if r['reason'])
    write_json(OUT / 'summary.json', dict(
        created_utc=now(), source_sha256=hashes, dropped_records=dict(dropped), panel_groups=len(group_rows),
        panel_groups_used=len(panels), panel_groups_excluded=dict(excluded), cohorts_considered=len(eligible),
        cohorts_not_eligible=dict(reasons), cohorts_eligible=sum(not r['reason'] for r in eligible),
        strata=len({r['stratum'] for r in chosen}), cohorts_selected=len(chosen), per_stratum=PER_STRATUM,
        calibration_datasets=datasets))
    print(json.dumps(dict(cohorts_selected=len(chosen), strata=len({r['stratum'] for r in chosen}),
                          datasets={k: v['units'] for k, v in datasets.items()}), indent=1))


if __name__ == '__main__':
    main()
