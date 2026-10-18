"""Add current TSM conditional date coverage without replacing sealed readiness."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_latest_conditional_input_readiness_20260919 as prior
from scripts import ndx_current_tsm_conditional_quote_20260919 as quote_reader
from scripts.ndx_base_three_cell_window_delta_research import publish
archive=prior.archive
BASE=ROOT/'data/cache/research'
PARENT=BASE/'latest_conditional_input_readiness_20260919_v1/readiness.json'
PARENT_SHA='b3a215d05cfb085c4637713d65fb86d565def48728cb382efe94ad1e206d3c49'
QUOTE=BASE/'current_tsm_raw_capture_20260919_v1/conditional_nominal_quotes_20260919.json'
QUOTE_SHA='b51abeb8b9ef5b1b5cf6f9b8b2a6aaf797091ec02a65f5297d7326c4f7fbc2a3'
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),Path(publish.__code__.co_filename).resolve())}
for mapping in (prior.LOADED,quote_reader.LOADED):archive.merge(LOADED,mapping)
FLAGS=('old_readiness_modified','original8_weights_changed','target_012922_changed','ndx_99_matrix_changed',
       'returns_generated','fit_performed','liquidity_verified','current_security_interval_binding_verified',
       'complete_actions_verified','point_in_time_verified','promotion_allowed','legal_comparison_ready')


def summarize(parent,quote):
    if (parent['schema']!='LATEST_PER_SECURITY_CONDITIONAL_INPUT_READINESS_V1'
        or quote['schema']!='INCUMBENT_TSM_FIXED_CUTOFF_CONDITIONAL_NOMINAL_QUOTE_V1'
        or parent['cutoff']!='2026-09-17' or quote['cutoff']!=parent['cutoff'] or quote['ticker']!='TSM'):
        raise ValueError('Exact fixed-cutoff inputs required')
    for k in ('price_identity_verified','complete_actions_verified','returns_generated','point_in_time_verified','promotion_allowed'):
        if quote[k] is not False:raise ValueError('Conditional quote scope upgraded')
    calendar=quote['calendar'];rows=quote['reconstruction']['rows']
    if (calendar!=sorted(set(calendar)) or not calendar or calendar[-1]!=parent['cutoff']
        or any(d>parent['cutoff'] for d in calendar) or [r['session'] for r in rows]!=calendar
        or type(quote['reconstruction']['row_count']) is not int or len(rows)!=quote['reconstruction']['row_count']):
        raise ValueError('Exact ordered conditional quote calendar required')
    original=parent['dual_benchmark_readiness']['original8']
    old,=[r for r in original['securities'] if r['ticker']=='TSM']
    coverage=prior.assess_calendar(reference=parent['observed_reference_calendar'],available=calendar,requirements=parent['requirements'])
    updated=deepcopy(original['securities'])
    for row in updated:
        if row['ticker']=='TSM':
            row['coverage']=coverage
            row['price_source_status']='CURRENT_TSM_CONDITIONAL_QUOTE_CHANNEL_NOT_LEGAL_RETURN_INPUT'
    return dict(schema='LATEST_TSM_CONDITIONAL_READINESS_ADDON_V1',cutoff=parent['cutoff'],
        requirements=deepcopy(parent['requirements']),reference_scope=parent['reference_scope'],
        original_tsm_entry=deepcopy(old),updated_original8_securities=updated,
        new_tsm_calendar_count=len(calendar),new_tsm_coverage=coverage,
        newly_covered_old_fit_missing_dates=[d for d in old['coverage']['windows']['latest_fit_adjacent_prices']['missing_dates'] if d in calendar],
        original8_all_fit_price_dates_covered=all(r['coverage']['windows']['latest_fit_adjacent_prices']['date_coverage_complete'] for r in updated),
        excluded_after_fixed_target=deepcopy(quote['excluded_after_fixed_target']),
        target_012922_status_retained=deepcopy(parent['dual_benchmark_readiness']['target_012922']),
        ndx_99_coverage_counts_retained={k:parent[k] for k in ('conditional_price_channels','fit_price_coverage_complete_count','minimum252_date_coverage_count','desired505_date_coverage_count','legal_fit_ready_count')},
        remaining_inputs=['Dated TSM ADR/security interval and provider identity binding','Legal adjusted-return basis and corporate-action completeness','Original 012922 publication-time and FX alignment','Liquidity volume values are not verified by date coverage'],
        input_artifact_binding_verified=False,**{k:False for k in FLAGS})


def verify(value):
    sources=value['historical_expected_source_hashes']
    required=dict(LOADED,**{str(PARENT):PARENT_SHA,str(QUOTE):QUOTE_SHA})
    if value['quote_reference']!=dict(path=str(QUOTE),sha256=QUOTE_SHA):raise ValueError('Hard TSM quote reference differs')
    if any(sources.get(p)!=h for p,h in required.items()):raise ValueError('Required source omitted')
    if any(value[k] is not False for k in FLAGS):raise ValueError('Coverage scope upgraded')
    if archive.verify_expected_sources(sources,archive.load_contract())!=value['archive_resolution']:raise ValueError('Archive source partition differs')


def build():
    sources=dict(LOADED)
    def read(path,h):
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=h:raise ValueError('External source SHA differs')
        archive.merge(sources,{str(path):h});return json.loads(raw)
    parent=read(PARENT,PARENT_SHA);quote=read(QUOTE,QUOTE_SHA)
    prior.verify(parent);quote_reader.verify(quote)
    for report in (parent,quote):archive.merge(sources,report['historical_expected_source_hashes'])
    result=summarize(parent,quote)
    result.update(parent_reference=dict(path=str(PARENT),sha256=PARENT_SHA),quote_reference=dict(path=str(QUOTE),sha256=QUOTE_SHA),
        input_artifact_binding_verified=True,historical_expected_source_hashes=sources,
        archive_resolution=archive.verify_expected_sources(sources,archive.load_contract()))
    verify(result);return result


def publish_verified(path,value):
    if Path(path).exists():raise FileExistsError('Create-only readiness addon')
    verify(value);saved=publish(path,value);verify(value);return saved


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    args=parser.parse_args();print(json.dumps(publish_verified(args.output,build())))
