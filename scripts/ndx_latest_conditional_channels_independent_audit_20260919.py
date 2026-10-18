"""Read the complete saved channel batch with a separate raw Decimal oracle."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_conditional_channel_independent_audit_research as oracle
from backtest import ndx_root_price_archive_contract_research as archive
from scripts import ndx_latest_conditional_channels_20260919 as recipe

ORACLE_SHA = 'e94f3c9a9cbc8d19fd4dd8f1b9cd73299f7d0c053e3e1580963bc12cff8c89e2'
SOURCE = Path(__file__).resolve()
LOADED = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
          for p in (SOURCE, Path(oracle.__file__).resolve(), archive.SOURCE)}


def exact(left, right):
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)


def read(reference, sources):
    if type(reference) is not dict or set(reference) != {'path', 'sha256'}:
        raise ValueError('Explicit file and external SHA required')
    path = Path(reference['path']).resolve(); raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != reference['sha256']:
        raise ValueError('Bound artifact bytes differ')
    archive.merge(sources, {str(path): reference['sha256']})
    return json.loads(raw, object_pairs_hook=oracle.unique)


def validate_index(index, plan_sha, folder, tasks):
    if (set(index) != {'schema', 'plan_sha256', 'output_directory', 'planned', 'completed', 'status', 'entries', *recipe.FALSE}
            or index['schema'] != 'LATEST_CHANNEL_INDEX_V1' or index['plan_sha256'] != plan_sha
            or index['output_directory'] != str(folder)
            or type(index['planned']) is not int or type(index['completed']) is not int
            or index['planned'] != 101 or index['completed'] != 101 or index['status'] != 'COMPLETE'
            or any(index[k] is not False for k in recipe.FALSE)):
        raise ValueError('Complete typed 101-channel index required')
    entries = index['entries']
    if (type(entries) is not list or len(entries) != 101 or len(tasks) != 101
            or len({t['ticker'] for t in tasks}) != 101
            or [e['ticker'] for e in entries] != [t['ticker'] for t in tasks]):
        raise ValueError('Exact full ordered task denominator required')
    for entry in entries:
        if (set(entry) != {'ticker', 'path', 'sha256', 'started_sha256'}
                or entry['path'] != str(folder / (entry['ticker'] + '.json'))):
            raise ValueError('Exact saved task address and fields required')


def validate_wrapper(value, task, plan_sha):
    expected = dict(schema='LATEST_CONDITIONAL_CHANNEL_TASK_V1', plan_sha256=plan_sha, task=task,
                    status='BLOCKED' if task['mode'] == 'BLOCKED' else 'CONDITIONAL_NUMERIC_RESULT',
                    result=value.get('result'), **dict.fromkeys(recipe.FALSE, False))
    if not exact(value, expected):
        raise ValueError('Typed task metadata or research scope differs')
    if task['mode'] == 'BLOCKED' and value['result'] is not None:
        raise ValueError('Blocked task cannot contain numerical output')
    if task['mode'] == 'CALCULATE' and type(value['result']) is not dict:
        raise ValueError('Numerical task must contain a complete channel output')


def build(*, plan_path, plan_sha256, index_path, index_sha256):
    if LOADED[str(Path(oracle.__file__).resolve())] != ORACLE_SHA:
        raise ValueError('Independently reviewed oracle changed')
    sources = dict(LOADED)
    plan_ref = dict(path=str(Path(plan_path).resolve()), sha256=plan_sha256)
    index_ref = dict(path=str(Path(index_path).resolve()), sha256=index_sha256)
    saved_plan = read(plan_ref, sources)
    plan, arguments = recipe.load_prepared()  # source preparation only; no numerical calculation
    if not exact(saved_plan, plan):
        raise ValueError('Full hard input plan does not reproduce')
    archive.merge(sources, plan['historical_expected_source_hashes'])
    index = read(index_ref, sources); folder = Path(index_path).resolve().parent
    validate_index(index, plan_sha256, folder, plan['tasks'])
    archive.verify_expected_sources(sources, archive.load_contract())
    details = []
    for entry, task in zip(index['entries'], plan['tasks']):
        marker = read(dict(path=str(folder / (task['ticker'] + '.started.json')),
                           sha256=entry['started_sha256']), sources)
        if not exact(marker, dict(schema='LATEST_CHANNEL_ATTEMPT_V1', plan_sha256=plan_sha256,
                                  task=task, attempt_count=1)):
            raise ValueError('Original typed exclusive attempt differs')
        value = read(dict(path=entry['path'], sha256=entry['sha256']), sources)
        validate_wrapper(value, task, plan_sha256)
        item = dict(ticker=task['ticker'], status=value['status'], reason=task['reason'], audit=None)
        if task['mode'] == 'CALCULATE':
            args = arguments[task['ticker']]
            payload = dict(args, raw_bytes_sha256=hashlib.sha256(args['raw_bytes']).hexdigest(), raw_bytes=None)
            if recipe.digest(payload) != task['input_sha256']:
                raise ValueError('Prepared raw/quote/calendar/event inputs changed')
            if value['result']['ticker'] != task['ticker']:
                raise ValueError('Saved output channel differs')
            item['audit'] = oracle.audit(output=value['result'], **{key: args[key] for key in (
                'raw_bytes', 'quote_rows', 'calendar', 'event_policy', 'exclude_on_or_after', 'regular_floor')})
        details.append(item)
    numeric = [r['audit'] for r in details if r['audit'] is not None]
    if len(numeric) != 96 or len(details) != 101:
        raise ValueError('Exact 101/96/5 audit denominator required')
    partition = archive.verify_expected_sources(sources, archive.load_contract())
    return dict(schema='LATEST_CONDITIONAL_CHANNELS_INDEPENDENT_AUDIT_V1', plan=plan_ref, index=index_ref,
                completed=101, numerical_channels=96, blocked_history_or_price=5, details=details,
                liquidity_unit_blocked=sum(r['liquidity_status'] == 'BLOCKED_VOLUME_UNIT_UNKNOWN' for r in numeric),
                historical_expected_source_hashes=sources, archive_resolution=partition,
                owner_source_preparation_reused=True, owner_numerical_kernel_called=False,
                security_identity_verified=False, complete_actions_verified=False,
                fit_performed=False, legal_training_input_admitted=False,
                point_in_time_verified=False, promotion_allowed=False)


def publish_verified(path, value):
    def verify():
        if any(value['historical_expected_source_hashes'].get(p) != h for p, h in LOADED.items()):
            raise ValueError('Auditor source binding omitted')
        if archive.verify_expected_sources(value['historical_expected_source_hashes'], archive.load_contract()) != value['archive_resolution']:
            raise ValueError('Audited source closure changed')
    verify(); saved = recipe.exclusive_publish(path, value); verify()
    return saved


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('plan-path', 'plan-sha256', 'index-path', 'index-sha256', 'output'):
        parser.add_argument('--' + key, required=True)
    args = vars(parser.parse_args()); output = args.pop('output')
    print(json.dumps(publish_verified(output, build(**args))))
