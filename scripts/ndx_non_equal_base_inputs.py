"""Independent base-task identities for revised non-equal fractional research."""
import csv
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_equal_weight_base_inputs as equal_base

SCHEMA = 'ndx_non_equal_base_task_v1'
SPECS = ('constrained_fixed_shrinkage', 'constrained_fixed_shrinkage_turnover_anchor')
_SOURCE = Path(__file__).resolve()
_LOADED = hashlib.sha256(_SOURCE.read_bytes()).hexdigest()
_EQUAL_LOADED = hashlib.sha256(Path(equal_base.__file__).read_bytes()).hexdigest()


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _definition(row, *, child, child_sha, csv_sha, source_batch, universe_track,
                selection_date, cutoff, semantics_sha, universe):
    if row['weight_spec'] not in SPECS:
        raise ValueError('Unsupported non-equal base specification')
    if (row['selection_date'] != selection_date or row['universe_track'] != universe_track
            or child['selection_date'] != selection_date or child['universe_track'] != universe_track
            or child['training_end'] != cutoff):
        raise ValueError('Base definition coordinate/cutoff differs')
    if not re.fullmatch('[1-9][0-9]*', row['holding_count']):
        raise ValueError('Canonical base cardinality required')
    k = int(row['holding_count'])
    if type(child['holding_count']) is not int or k != child['holding_count']:
        raise ValueError('Base cardinality differs from child')
    tickers = row['tickers'].split(';')
    if (len(tickers) != k or tickers != sorted(set(tickers))
            or any(not t or t != t.strip().upper() or t not in universe for t in tickers)):
        raise ValueError('Invalid base ticker identities')
    identities = [universe[t] for t in tickers]
    for item in identities:
        for key in ('security_id', 'issuer_id', 'risk_chain'):
            value = item[key]
            if type(value) is not str or not value or value != value.strip():
                raise ValueError('Canonical context identity required')
    if (len({item['security_id'] for item in identities}) != k
            or len({item['issuer_id'] for item in identities}) != k):
        raise ValueError('Duplicate security or issuer in base combination')
    portfolio = hashlib.sha256((row['weight_spec']+'|'+row['tickers']).encode()).hexdigest()[:16]
    if row['portfolio_id'] != portfolio:
        raise ValueError('Saved base portfolio identity differs')
    identity = dict(schema_version=SCHEMA, source_batch=source_batch, universe_track=universe_track,
        selection_date=selection_date, decision_data_end=cutoff, holding_count=k,
        tickers=row['tickers'], weight_spec=row['weight_spec'],
        source_child_sha256=child_sha, source_candidates_sha256=csv_sha,
        source_portfolio_id=portfolio, training_semantics_sha256=semantics_sha)
    return dict(identity, job_id=_sha(identity))


def prepare_non_equal_base_date(*, source_batch, universe_track, selection_date):
    for path, digest in ((_SOURCE, _LOADED), (Path(equal_base.__file__), _EQUAL_LOADED)):
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Loaded base preparation source drift')
    if type(selection_date) is not str or date.fromisoformat(selection_date).isoformat() != selection_date:
        raise ValueError('Canonical selection date required')
    prepared = equal_base.prepare_equal_base_date(source_batch=source_batch,
        universe_track=universe_track, selection_date=selection_date)
    inventory = equal_base.inventory_date(source_batch=source_batch,
        universe_track=universe_track, selection_date=selection_date)
    inputs = prepared['inputs']
    cutoff = str(inputs['returns'].index[-1].date())
    if cutoff >= selection_date:
        raise ValueError('Training cutoff must precede execution')
    sources = {}
    for path, digest in prepared['source_hashes'].items():
        key = str(Path(path).resolve())
        if key in sources and sources[key] != digest:
            raise ValueError('Conflicting normalized source identity')
        sources[key] = digest
    sources[str(_SOURCE)] = _LOADED
    universe_frame = inputs['universe']
    if not universe_frame.ticker.is_unique or not universe_frame.security_id.is_unique:
        raise ValueError('Ambiguous context universe')
    universe = universe_frame.set_index('ticker').to_dict('index')
    tasks = []; seen = set()
    # The complete readiness closure includes other dates' files. Only the
    # requested date inventory defines candidates; never iterate that closure.
    for name, digest in inventory['source_hashes'].items():
        path = Path(name)
        if path.name != 'training_candidates.csv':
            continue
        if sources.get(str(path.resolve())) != digest:
            raise ValueError('Date inventory differs from prepared source closure')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('Base candidate source changed')
        child_path = path.parent/'manifest.json'
        child_sha = sources.get(str(child_path.resolve()))
        child_raw = child_path.read_bytes()
        if child_sha is None or hashlib.sha256(child_raw).hexdigest() != child_sha:
            raise ValueError('Missing/broken bound child manifest')
        child = json.loads(child_raw)
        descriptor = child['artifacts']['candidates']
        if descriptor['sha256'] != digest or Path(descriptor['path']).resolve() != path.resolve():
            raise ValueError('Child candidate descriptor mismatch')
        rows = list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
        if not rows or len(set(rows[0])) != len(rows[0]) or any(len(r) != len(rows[0]) for r in rows[1:]):
            raise ValueError('Invalid base CSV header/width')
        if len(rows)-1 != descriptor['rows']:
            raise ValueError('Base source denominator differs')
        for values in rows[1:]:
            row = dict(zip(rows[0], values))
            if row['weight_spec'] == 'equal_weight':
                continue
            task = _definition(row, child=child, child_sha=child_sha, csv_sha=digest,
                source_batch=source_batch, universe_track=universe_track, selection_date=selection_date,
                cutoff=cutoff, semantics_sha=prepared['training_semantics']['training_semantics_sha256'], universe=universe)
            key = (task['tickers'], task['weight_spec'])
            if key in seen:
                raise ValueError('Duplicate non-equal base definition')
            seen.add(key); tasks.append(task)
    expected = prepared['summary']['all_base_count'] - prepared['summary']['equal_weight_base_count']
    if len(tasks) != expected or len({t['job_id'] for t in tasks}) != len(tasks):
        raise ValueError('Non-equal base denominator differs')
    tasks.sort(key=lambda t: (t['holding_count'], t['tickers'], t['weight_spec']))
    if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != h for p, h in sources.items()):
        raise ValueError('Base preparation source changed during read')
    return dict(inputs=inputs, tasks=tasks, source_hashes=sources,
        training_semantics=prepared['training_semantics'], summary=dict(
            non_equal_base_count=len(tasks), all_base_count=prepared['summary']['all_base_count'],
            equal_weight_base_count=prepared['summary']['equal_weight_base_count'],
            delta_count=prepared['summary']['delta_count'],
            task_schema=SCHEMA, task_set_sha256=_sha(tasks),
            cardinalities=sorted({task['holding_count'] for task in tasks}),
            old_economic_metrics_used=False, economic_evaluation_performed=False,
            delta_namespace_reused=False, promotion_allowed=False))
