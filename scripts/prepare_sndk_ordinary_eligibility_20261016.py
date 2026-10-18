"""Isolated ordinary-only SNDK history convention; preserves all original data."""
import copy
import gzip
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
BASE = 'tmp/conditional_calendar_year_inputs_20261016_v2'
PROPOSAL = 'tmp/wdc_sndk_distribution_evidence_20261016_v1/channel_conditional_admission_proposal.json'


def prepare(output):
    directory = (ROOT / output).resolve()
    if not directory.is_relative_to(ROOT / 'tmp') or directory.exists():
        raise ValueError('NEW_TMP_OUTPUT_REQUIRED')
    pins = {}

    def read(path, expected=None):
        raw = (ROOT / path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected is not None and digest != expected:
            raise ValueError('SOURCE_DRIFT')
        pins[path] = digest
        return raw

    proposal = json.loads(read(PROPOSAL))
    for path, digest in proposal['source_hashes'].items():
        read(path, digest)
    ordinary = next(row for row in proposal['official_identifiers']
                    if row['role'] == 'CHILD_ORDINARY_AND_PENDING_RIGHT_MARK')
    start = ordinary['start']
    source = 'data/cache/research/current_raw_capture_20261014_v1/SNDK.response.bin'
    raw = read(source)
    chart = json.loads(gzip.decompress(raw), parse_float=str)['chart']['result'][0]
    dates = [datetime.fromtimestamp(ts, ZoneInfo(chart['meta']['exchangeTimezoneName'])).date().isoformat()
             for ts in chart['timestamp']]
    excluded = [day for day in dates if day < start]
    if len(excluded) != 6 or start != '2025-02-24':
        raise ValueError('EXPECTED_REVIEWED_BOUNDARY_DIFFERS')
    all_original, all_corrected, outputs = [], [], {}
    calendars = []
    for year in (2024, 2025, 2026):
        calendar = json.loads(read(f'{BASE}/{year}_calendar.json'))
        calendars += calendar['sessions']
        original = json.loads(read(f'{BASE}/{year}_eligibility.json'))
        corrected = copy.deepcopy(original)
        for row in corrected:
            affected = [day for day in excluded if row['training_start'] <= day <= row['training_end']]
            if not affected:
                continue
            if 'SNDK' in row['price_history_ready']:
                row['price_history_ready'].remove('SNDK')
            existing = next((item for item in row['excluded'] if item['ticker'] == 'SNDK'), None)
            if existing is None:
                existing = dict(ticker='SNDK', missing_dates=[])
                row['excluded'].append(existing)
            existing.update(reason='INSUFFICIENT_253_ORDINARY_ONLY_CLOSES',
                            classification='EXPLICIT_ORDINARY_ONLY_CONVENTION_NOT_WI_PREDICTIVENESS_CLAIM',
                            ordinary_start=start, when_issued_dates_excluded=affected)
            existing['missing_dates'] = sorted(set(existing['missing_dates']) | set(affected))
            existing['missing_count'] = len(existing['missing_dates'])
            assert len(row['price_history_ready']) + len(row['excluded']) == 101
        outputs[f'{year}_eligibility.json'] = corrected
        all_original += original
        all_corrected += corrected
    affected = [old['signal_date'] for old, new in zip(all_original, all_corrected)
                if ('SNDK' in old['price_history_ready']) != ('SNDK' in new['price_history_ready'])]
    monthly = {day for index, day in enumerate(calendars[:-1])
               if day[:7] != calendars[index + 1][:7]}
    training_path = 'tmp/next12_training_prepare_20261014_v1/prepared.json'
    training = json.loads(read(training_path))
    next12 = []
    for window in training['windows']:
        candidates = [r for r in window['candidates'] if r['ticker'] == 'SNDK']
        overlap = sorted(set(excluded) & set(window['training_dates'])) if candidates else []
        next12.append(dict(decision=window['decision_cutoff'], sndk_in_domain=bool(candidates),
                           preordinary_dates_used=overlap))
    current_path = 'tmp/monthly_captured_training_20261014_v2/input.json'
    current = json.loads(read(current_path))
    current_source = next(value['path'] for value in current['bar_sources'].values() if 'SNDK.response.bin' in value['path'])
    current_raw = read(current_source)
    current_chart = json.loads(gzip.decompress(current_raw))['chart']['result'][0]
    current_dates = [datetime.fromtimestamp(ts, ZoneInfo('America/New_York')).date().isoformat()
                     for ts in current_chart['timestamp']]
    summary = dict(schema='SNDK_ORDINARY_ONLY_ELIGIBILITY_REVISION_V1', ordinary_start=start,
        convention='ORDINARY_ONLY_HISTORICAL_RESEARCH; WI_MAY_BE_PREDICTIVE_BUT_NOT_THIS_INSTRUMENT_SERIES',
        excluded_when_issued_dates=excluded, original_raw_retained=source,
        original_first_253=next(r['signal_date'] for r in all_original if 'SNDK' in r['price_history_ready']),
        revised_first_253=next(r['signal_date'] for r in all_corrected if 'SNDK' in r['price_history_ready']),
        affected_daily_decisions=affected, affected_month_end_decisions=sorted(set(affected) & monthly),
        next12_review=next12, current_source_first=current_dates[0],
        current_preordinary_dates=sorted(set(current_dates) & set(excluded)),
        no_repeated_exclusion_required_for_saved_next12_or_current=not any(r['preordinary_dates_used'] for r in next12) and not (set(current_dates) & set(excluded)),
        original_domain_count=101, domain_filtered=False, execution_before_ordinary_start_allowed=False,
        scope='Only isolated annual eligibility revised; sealed next12/current unchanged. No claim their code explicitly applied this boundary.',
        economic_calls=0, execution_admitted=False)
    read(Path(__file__).relative_to(ROOT).as_posix())
    for path, digest in list(pins.items()):
        read(path, digest)
    summary['source_hashes'] = pins
    directory.mkdir()
    for filename, rows in outputs.items():
        (directory / filename).write_text(json.dumps(rows, indent=2), encoding='utf-8')
    (directory / 'revision_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps({key: summary[key] for key in ('original_first_253','revised_first_253','affected_daily_decisions','affected_month_end_decisions')}))


if __name__ == '__main__':
    prepare(sys.argv[1])
