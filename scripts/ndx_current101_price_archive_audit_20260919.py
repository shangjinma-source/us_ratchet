"""Independent saved-price arithmetic with explicit immutable archive resolution.

No producer/guard is invoked. The original reader remains strict and unchanged.
Only its pure raw parsing, request and Decimal arithmetic functions are reused.
"""
import argparse
import json
import os
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_current101_price_independent_audit_20260919 as pure
from backtest import ndx_root_price_archive_contract_research as archive

SOURCE = Path(__file__).resolve()
LOADED = dict(pure.LOADED)
LOADED.update({str(SOURCE): pure.drift.file_sha(SOURCE), str(archive.SOURCE): archive.LOADED})
SCHEMA = 'CURRENT101_FINAL_PRICE_ARCHIVE_RESOLVED_INDEPENDENT_AUDIT_V1'


def bind(destination, addition):
    archive.merge(destination, addition)


def partition(sources, contract):
    value = archive.verify_expected_sources(sources, contract)
    if len(value['archive_resolutions']) != 85 or len(value['historical_gap_observations']) != 26:
        raise ValueError('Exact 85 preserved / 26 unresolved archive partition required')
    return value


def validate_historical_plan_gaps(plan, contract):
    """Compare historical observations to sealed bytes, never current root CSVs."""
    old = pure.drift.load_contract()
    # Original verifier specifies the observation shape and deterministic order.
    actual = plan['historical_price_cache_gap_observations']
    by_path = {r['path']: r for r in actual}
    if len(by_path) != 26 or set(by_path) != set(old['exceptions']):
        raise ValueError('Original exact 26 observation denominator differs')
    for p, gap in old['exceptions'].items():
        row = by_path[p]
        expected = dict(gap, path=p, historical_bytes_verified=False, current_observation_unchanged=True)
        if (pure.canonical(row) != pure.canonical(expected)
                or plan['historical_expected_source_hashes'].get(p) != gap['expected_historical_sha256']
                or contract['rows'][p]['archived_sha256'] != gap['observed_current_sha256']):
            raise ValueError('Original observation must equal sealed observation, not live cache')


def build(*, index_path, index_sha256):
    if Path(index_path).resolve() != pure.INDEX or index_sha256 != pure.INDEX_SHA:
        raise ValueError('Hard final execution index required')
    sources = dict(LOADED)

    def read(path, sha):
        path = str(Path(path).resolve())
        raw = Path(path).read_bytes()
        if pure.digest(raw) != sha:
            raise ValueError('External bound bytes differ: ' + path)
        bind(sources, {path: sha})
        return pure.loads(raw)

    plan = read(pure.PLAN, pure.PLAN_SHA)
    index = read(index_path, index_sha256)
    pure.validate_index(index, plan)
    bind(sources, plan['historical_expected_source_hashes'])
    contract = archive.load_contract()
    validate_historical_plan_gaps(plan, contract)
    partition(sources, contract)
    reports, common, all_raw_common = [], None, None
    maximum = Decimal(0)
    for task, entry in zip(plan['tasks'], index['entries']):
        doc = read(entry['path'], entry['sha256'])
        if (any(pure.canonical(doc.get(k)) != pure.canonical(v) for k, v in task.items())
                or doc['plan_sha256'] != pure.PLAN_SHA or any(doc.get(k) is not False for k in pure.FALSE_FIELDS)):
            raise ValueError('Task identity/disclosure differs')
        path = Path(task['raw_path'])
        raw = path.read_bytes()
        if pure.digest(raw) != task['raw_sha256'] or sources.get(str(path)) != task['raw_sha256']:
            raise ValueError('Hard planned raw differs')
        receipt_path = path.parent / (task['ticker'] + '.receipt.json')
        receipt = read(receipt_path, sources[str(receipt_path)])
        started = read(path.parent / (task['ticker'] + '.started.json'), receipt['started_sha256'])
        info = pure.inspect_raw(raw, task['ticker'])
        pure.verify_request(task, receipt, started, info)
        parsed_path = path.parent / (task['ticker'] + '.decoded.json')
        parsed = read(parsed_path, sources[str(parsed_path)])
        if (receipt['raw_sha256'] != task['raw_sha256'] or receipt['raw_bytes'] != len(raw)
                or parsed['decoded_sha256'] != info['decoded_sha256'] or parsed['ticker'] != task['ticker']
                or parsed['receipt_sha256'] != sources[str(receipt_path)]):
            raise ValueError('Original body/decode receipt differs')
        completed = [d for i, d in enumerate(info['days']) if d < task['exclude_on_or_after']
                     and all(type(info['quotes'][k][i]) in (int, float)
                             and pure.math.isfinite(info['quotes'][k][i]) and info['quotes'][k][i] > 0
                             for k in ('open', 'close'))]
        all_raw_common = set(completed) if all_raw_common is None else all_raw_common & set(completed)
        item = dict(ticker=task['ticker'], mode=task['mode'], raw_slot_count=len(info['days']),
                    valid_completed_raw_count=len(completed), valid_completed_raw_first=completed[0] if completed else None,
                    valid_completed_raw_last=completed[-1] if completed else None,
                    receipt_day_excluded=task['exclude_on_or_after'],
                    unfinalized_raw_dates=[d for d in info['days'] if d >= task['exclude_on_or_after']],
                    returned_split_events=info['events'], returned_dividend_count=len(info['data'].get('events', {}).get('dividends', {})),
                    provider_history_starts_after_20220103=info['days'][0] > '2022-01-03')
        if task['mode'] == 'BLOCKED_COMPLEX_OR_IDENTITY':
            if doc['status'] != 'BLOCKED' or doc.get('reconstruction', 'MISSING') is not None or 'result' in doc:
                raise ValueError('Blocked must have no price output')
            item.update(status='EXPLICITLY_BLOCKED_NOT_MISSING_PRICE', output_row_count=0)
        else:
            if doc['status'] != 'CONDITIONAL_PRICE_NOT_IDENTITY':
                raise ValueError('Conditional output status required')
            result = doc['result']
            reconstruction = result['reconstruction']
            if any(result.get(k) is not False for k in ('price_identity_verified', 'point_in_time_verified', 'promotion_allowed',
                                                       'returns_generated', 'training_performed', 'historical_full_source_closure_verified')):
                raise ValueError('Nested false scope upgraded')
            if task['mode'] == 'REFERENCE_EXISTING_REGULAR':
                reference = read(task['reference']['path'], task['reference']['sha256'])
                if pure.canonical(reference) != pure.canonical(result) or result['regular_way_floor'] != pure.FLOORS[task['ticker']]:
                    raise ValueError('Existing regular reference differs')
            elif result['schema'] != 'CURRENT_RECEIPT_28_SPECIFIC_EVENT_QUOTE_GUARD_V1':
                raise ValueError('Exact conditional guard scope required')
            if (reconstruction['ticker'] != task['ticker'] or type(reconstruction['row_count']) is not int
                    or reconstruction['row_count'] != len(reconstruction['rows']) or reconstruction['quote_field_basis'] != pure.BASIS
                    or reconstruction['adjclose_used'] is not False or reconstruction['dividends_applied_to_quote'] is not False):
                raise ValueError('Nominal quote basis/denominator differs')
            audited = pure.audit_rows(rawinfo=info, task=task, rows=reconstruction['rows'])
            maximum = max(maximum, Decimal(audited['maximum_absolute_decimal_error']))
            common = set(audited['calendar']) if common is None else common & set(audited['calendar'])
            item.update(status='CONDITIONAL_PRICE_ARITHMETIC_VERIFIED_NOT_IDENTITY', **audited)
        reports.append(item)
    checked = partition(sources, contract)
    result = dict(schema=SCHEMA, index=dict(path=str(pure.INDEX), sha256=pure.INDEX_SHA),
                  plan=dict(path=str(pure.PLAN), sha256=pure.PLAN_SHA), rows=reports, completed_task_count=101,
                  conditional_price_channel_count=95, blocked_channel_count=6, mode_counts=pure.MODES,
                  maximum_absolute_decimal_error=str(maximum), common_95_conditional_provider_calendar=sorted(common),
                  common_101_valid_raw_provider_calendar=sorted(all_raw_common),
                  short_provider_history_tickers=[r['ticker'] for r in reports if r['provider_history_starts_after_20220103']],
                  regular_partition_tickers=sorted(pure.FLOORS), historical_expected_source_hashes=sources,
                  archive_resolution=checked, original_live_root_paths_verified=False,
                  original_strict_reader_passed=False, original_26_observations_asserted_live_unchanged=False,
                  reconstruction_guard_called=False, reported_factor_used_for_decimal_recalculation=False,
                  provider_calendar_is_exchange_calendar=False, provider_start_date_is_verified_ipo_date=False,
                  complete_corporate_action_history_verified=False, price_identity_verified=False,
                  historical_full_source_closure_verified=False, returns_generated=False, training_performed=False,
                  point_in_time_verified=False, promotion_allowed=False)
    verify(result)
    return result


def verify(report):
    if report.get('schema') != SCHEMA or any(report.get(k) is not False for k in (
            'original_live_root_paths_verified', 'original_strict_reader_passed', 'original_26_observations_asserted_live_unchanged',
            'historical_full_source_closure_verified', 'price_identity_verified', 'point_in_time_verified', 'promotion_allowed')):
        raise ValueError('Archive resolution disclosure differs')
    sources = report['historical_expected_source_hashes']
    if any(sources.get(p) != h for p, h in LOADED.items()):
        raise ValueError('Loaded auditor source omitted')
    checked = partition(sources, archive.load_contract())
    if pure.canonical(checked) != pure.canonical(report['archive_resolution']):
        raise ValueError('Immutable archive partition differs')


def publish(path, report):
    verify(report)
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf8') as stream:
            json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        verify(report)
        os.link(temporary, path)
    finally:
        os.unlink(temporary)
    verify(report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('index-path', 'index-sha256', 'output'):
        parser.add_argument('--' + key, required=True)
    args = parser.parse_args()
    report = build(index_path=args.index_path, index_sha256=args.index_sha256)
    publish(args.output, report)
    print(json.dumps(dict(path=str(Path(args.output).resolve()), sha256=pure.drift.file_sha(args.output))))
