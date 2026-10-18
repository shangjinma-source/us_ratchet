"""One new-asof incumbent TSM request, preserving the old receipt and all caches."""
import argparse
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_current_22_price_capture_20260919 as capture
from scripts import ndx_current79_new_asof_capture_20260919 as newer
from scripts.ndx_base_three_cell_window_delta_research import publish

OLD = ROOT / 'data/cache/research/incumbent_price_source_probe_20260912_v1/manifest.json'
OLD_SHA = '4e30f0f7e48b157eb4a5f60cd5d6531b097d2a276f977444838778411e30d77e'
OUTPUT = ROOT / 'data/cache/research/current_tsm_raw_capture_20260919_v1'
SOURCE = Path(__file__).resolve()
LOADED = {str(p): capture.digest(p.read_bytes()) for p in (
    SOURCE, Path(capture.__file__).resolve(), Path(newer.__file__).resolve(), Path(publish.__code__.co_filename).resolve())}


def build_plan():
    prior = capture.read_bound(OLD, OLD_SHA)
    row, = [r for r in prior['probes'] if r['name'] == 'yahoo_tsm_through_received_daily_events']
    url = row['request']['url']; parsed = urlparse(url); query = parse_qs(parsed.query)
    if parsed.netloc != 'query1.finance.yahoo.com' or parsed.path != '/v8/finance/chart/TSM':
        raise ValueError('Exact old incumbent channel required')
    sources = dict(LOADED, **{str(OLD): OLD_SHA, row['response_path']: row['response_sha256']})
    newer.verify(sources)
    return dict(schema='INCUMBENT_TSM_NEW_ASOF_RAW_PLAN_V1', ticker='TSM', prior_request_url=url,
        prior_max_request_period2=int(query['period2'][0]), original_raw_path=row['response_path'],
        original_raw_sha256=row['response_sha256'], period1=1640995200,
        target_completed_cutoff='2026-09-17', output_directory=str(OUTPUT), maximum_attempts=1,
        source_hashes=sources, purpose='LATEST_ORIGINAL_INCUMBENT_INPUT_GAP_RAW_CAPTURE',
        ndx_membership_claimed=False, old_receipt_modified=False, root_cache_modified=False,
        returns_generated=False, training_performed=False, point_in_time_verified=False, promotion_allowed=False)


def execute(plan_path, plan_sha256, opener=urlopen):
    plan = capture.read_bound(plan_path, plan_sha256)
    if plan != build_plan() or Path(plan_path).resolve() != OUTPUT / 'plan.json':
        raise ValueError('Exact reviewed isolated plan required')
    if any(OUTPUT.glob('TSM.*')) or (OUTPUT / 'index.json').exists():
        raise FileExistsError('Existing attempt; read evidence instead of retrying HTTP')
    coordinate = dict(ticker='TSM', prior_max_request_period2=plan['prior_max_request_period2'])
    entry = newer.capture_one(coordinate, OUTPUT, plan_sha256, {plan['prior_request_url']}, opener)
    newer.verify(plan['source_hashes'])
    receipt = capture.read_bound(entry['receipt_path'], entry['receipt_sha256'])
    report = dict(schema='INCUMBENT_TSM_NEW_ASOF_RAW_INDEX_V1', plan=dict(path=str(plan_path), sha256=plan_sha256),
        entry=entry, http_status=receipt.get('http_status'), source_hashes=plan['source_hashes'],
        target_completed_cutoff=plan['target_completed_cutoff'], received_at_utc=receipt['received_at_utc'],
        receipt_calendar_excludes_on_or_after=receipt['completed_training_excludes_dates_on_or_after'],
        ndx_membership_claimed=False, price_identity_verified=False, returns_generated=False,
        training_performed=False, point_in_time_verified=False, promotion_allowed=False)
    saved = publish(OUTPUT / 'index.json', report)
    newer.verify(plan['source_hashes'])
    return dict(saved, http_status=receipt.get('http_status'), attempt_count=1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true'); parser.add_argument('--plan-sha256')
    args = parser.parse_args(); target = OUTPUT / 'plan.json'
    if args.execute:
        if not args.plan_sha256: parser.error('External plan SHA required')
        result = execute(target, args.plan_sha256)
    else:
        if target.exists(): raise FileExistsError('Plan already exists; verify rather than overwrite')
        result = dict(publish(target, build_plan()), network_requests=0)
    print(json.dumps(result))
