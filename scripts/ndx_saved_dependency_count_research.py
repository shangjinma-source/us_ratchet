"""Read saved records only; classify a single evidenced return-cell dependency."""
from collections import Counter
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()
LOADED = hashlib.sha256(SELF.read_bytes()).hexdigest()


def run():
    sources = {}
    def read(path, expected=None):
        path = Path(path).resolve()
        raw = path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        if expected is not None and sha != expected:
            raise ValueError('Source changed: ' + str(path))
        if str(path) in sources and sources[str(path)] != sha:
            raise ValueError('Conflicting source')
        sources[str(path)] = sha
        return raw
    def obj(path, expected=None):
        return json.loads(read(path, expected))
    read(SELF, LOADED)
    gap = obj(ROOT / 'data/cache/research/full_history_gap_source_probe_20260912_v1/gap_review_20260912.json',
              '9945c989d24489f4fc3224ce86ddcc9dc142af67f54c4f0bd918141d67d87ade')
    for path, digest in gap['source_hashes'].items():
        read(path, digest)
    base = ROOT / 'data/cache/research/full_history_gap_source_probe_20260912_v1'
    manifest = obj(base / 'manifest.json')
    panels = {}
    for probe in manifest['probes']:
        if not probe['name'].startswith('yahoo_'):
            continue
        raw = read(probe['response_path'], probe['response_sha256'])
        if raw[:2] == b'\x1f\x8b': raw = gzip.decompress(raw)
        result, = json.loads(raw)['chart']['result']
        dates = [datetime.fromtimestamp(t, ZoneInfo('America/New_York')).date().isoformat()
                 for t in result['timestamp']]
        panels[result['meta']['symbol']] = set(dates)
    calendar = sorted(panels['DASH'])
    previous = dict(zip(calendar[1:], calendar[:-1]))
    gap_rows = []
    for cohort in gap['first_last_cohorts']:
        paths = [p for p, h in gap['source_hashes'].items()
                 if h == cohort['context_sha256'] and Path(p).name == 'context.json']
        path, = paths
        context = obj(path, cohort['context_sha256'])
        dates = [x['timestamp'][:10] for x in context['prepared_inputs']['returns']['payload']['mapping']['index']['items']]
        for row in cohort['rows']:
            ticker = row['ticker']
            missing = [d for d in dates if d not in panels[ticker] or previous[d] not in panels[ticker]]
            unresolved = [d for d in dates if ticker == 'WBD' and previous[d] < '2022-04-11']
            if missing != row['raw_missing_adjacent_price_return_dates'] or unresolved != row['predecessor_class_binding_unresolved_return_dates']:
                raise ValueError('Independent adjacent-date gap differs')
            if row['historical_identity_join_authorized'] is not False or row['complete_training_input_authorized'] is not False:
                raise ValueError('Unsupported promotion')
            gap_rows.append(dict(date=cohort['coordinate']['selection_date'], ticker=ticker,
                                 missing_return_dates=missing, unresolved_predecessor_dates=unresolved))
    inventory = obj(ROOT / 'data/cache/research/dynamic_frozen_v2/combined_summary_inventory_20260912.json')
    sensitivity = obj(ROOT / 'data/cache/research/root_return_semantics_probe_20260912_v1/candidate_window_impact_v2_20260912.json',
        'e7afce67cf017f074af2ceff574b5010cc13d1addbd99021866ff74e590ddeb9')
    for path, digest in sensitivity['source_hashes'].items(): read(path, digest)
    locations = {r['coordinate']['selection_date']: r for r in sensitivity['rows']}
    counts = Counter(); by_date = {}; checkpoints = {}; samples = {}
    def add(date, origin, tickers, weight_spec, status):
        selected = 'GOOG' in (tickers.split(';') if isinstance(tickers, str) else tickers)
        location = locations[date]
        forward = location['known_error_forward_window_count'] > 0
        fitted = weight_spec != 'equal_weight'
        selected_affected = selected and (forward or fitted and location['known_error_fit_window_count'] > 0)
        category = ('SELECTED_NUMERICAL_INPUT_CHANGED' if selected_affected else
                    'INCUMBENT_PAIRED_ONLY_CHANGED' if forward else 'NO_DEPENDENCY_ON_THIS_CELL')
        key = '|'.join((origin, category, status))
        counts[key] += 1
        by_date.setdefault(date, Counter())[key] += 1
    for descriptor in inventory['summaries']:
        saved = obj(descriptor['path'], descriptor['sha256'])
        date = descriptor['coordinate']['selection_date']
        paths = [p for p in saved['source_hashes'] if Path(p).name.startswith('equal_base_')]
        path, = paths
        equal = obj(path, saved['source_hashes'][path])
        if len(equal['evaluation']['records']) != saved['counts']['EQUAL_WEIGHT_BASE']['observed']:
            raise ValueError('Equal denominator differs')
        for record in equal['evaluation']['records']:
            add(date, 'EQUAL_WEIGHT_BASE', record['tickers'], record['weight_spec'], 'EVALUATED')
        samples.setdefault('EQUAL_WEIGHT_BASE', dict(path=path, record_fields=list(equal['evaluation']['records'][0]),
            economic_fields=list(equal['evaluation']['records'][0]['fractional_metrics'])))
        for path, digest in saved['source_hashes'].items():
            if Path(path).name == 'context.json': continue
            if 'ndx_non_equal_base_fractional_v1' in path or 'ndx_joint_weight_runs_v3' in path:
                if path in checkpoints and checkpoints[path] != digest: raise ValueError('Checkpoint SHA conflict')
                checkpoints[path] = digest
    for path, digest in checkpoints.items():
        checkpoint = obj(path, digest)
        task = checkpoint['task']; date = task['selection_date']
        if date not in locations: raise ValueError('Unexpected date')
        origin = 'NON_EQUAL_BASE' if 'ndx_non_equal_base_fractional_v1' in path else 'DELTA'
        add(date, origin, task['tickers'], task['weight_spec'], checkpoint['status'])
        if origin not in samples:
            result = checkpoint['result']['mapping']
            economic = result['result']['mapping'] if origin == 'NON_EQUAL_BASE' else result
            samples[origin] = dict(path=path, result_fields=list(result), economic_fields=list(economic))
    if sum(counts.values()) != inventory['record_count'] or inventory['record_count'] != 351255 or len(by_date) != 15:
        raise ValueError('Complete saved-record denominator differs')
    for descriptor in inventory['summaries']:
        row = by_date[descriptor['coordinate']['selection_date']]
        for origin, expected in descriptor['counts'].items():
            if sum(n for key,n in row.items() if key.startswith(origin+'|')) != expected['observed']:
                raise ValueError('Per-date origin denominator differs')
    for path, digest in list(sources.items()): read(path, digest)
    return dict(schema='ndx_saved_dependency_count_research_v1', source_hashes=sources,
        gap_independent_rows=gap_rows, gap_source_count=len(gap['source_hashes']),
        record_count=sum(counts.values()), counts=dict(counts), by_date={d:dict(c) for d,c in by_date.items()},
        checkpoint_field_samples=samples, assumption='ONLY_GOOG_20220718_RETURN_CELL_CHANGED_ALL_OTHER_INPUTS_IDENTICAL',
        classifications_are_dependency_not_recomputed_economic_outcomes=True,
        previous_weight_anchor_and_turnover_propagation_included=True,
        quantile_subtraction_is_valid_paired_reconstruction=False,
        history_training_performed=False, old_checkpoints_modified=False,
        checkpoint_reuse_authorized=False, point_in_time_verified=False, promotion_allowed=False)


if __name__ == '__main__':
    result = run()
    path = ROOT / 'data/cache/research/root_return_semantics_probe_20260912_v1/saved_dependency_count_20260912.json'
    raw = (json.dumps(result, indent=2, sort_keys=True)+'\n').encode()
    with path.open('xb') as stream: stream.write(raw)
    for source, digest in result['source_hashes'].items():
        if hashlib.sha256(Path(source).read_bytes()).hexdigest() != digest: raise ValueError('Source drift after save')
    print(json.dumps(dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(), counts=result['counts'])))
