"""Preparation/helper draft only; superseded by evidenced multi-cell delta entry."""
from copy import deepcopy
from datetime import datetime
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_equal_weight_base_report as old_report
from scripts import ndx_equal_weight_base_inputs as preparation
from backtest import ndx_equal_weight_fractional_batch as evaluator
from backtest import ndx_joint_weight_runner as encoding

SOURCE=Path(__file__).resolve()
LOADED={str(Path(module.__file__).resolve()):hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
        for module in (old_report,preparation,evaluator,encoding)}
LOADED[str(SOURCE)]=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
INVENTORY=ROOT/'data/cache/research/dynamic_frozen_v2/combined_summary_inventory_20260912.json'
INVENTORY_SHA='baa74f6447e4663ac13a0b4174ad0fa0cf0d799ce3d35a735c9f25379e24ca09'
CORRECTION=ROOT/'data/cache/research/root_return_semantics_probe_20260912_v1/root_return_semantics_review_20260912.json'
CORRECTION_SHA='a0cfca247b790779de4abdfa8ce4d284214cf4405e35e1fb38233f018db6c02b'
DAY='2022-07-18'
VALUE=-0.025335378898117544
DATES=('2023-04-03','2023-05-01','2023-06-01','2023-07-03','2023-08-01','2023-09-01',
       '2023-10-02','2023-11-01','2023-12-01','2024-01-02','2024-02-01','2024-03-01',
       '2024-04-01','2024-05-01','2024-06-03')
ALLOWED_METRICS={'return_p50','return_p10','max_drawdown_p50','max_drawdown_p90',
    'paired_return_p50_vs_incumbent','paired_return_p10_vs_incumbent',
    'paired_drawdown_cost_p50_vs_incumbent','paired_drawdown_cost_p90_vs_incumbent',
    'return_p50_vs_012922','return_p10_vs_012922','max_drawdown_p50_vs_012922',
    'max_drawdown_p90_vs_012922','target_012922_distance'}


def bound(path,digest):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Bound source differs: '+str(path))
    return json.loads(raw,object_pairs_hook=old_report._object)


def typed_digest(value):
    if isinstance(value,dict) and any(isinstance(item,(pd.DataFrame,pd.Series)) for item in value.values()):
        value={key:encoding._panel_context(item) for key,item in value.items()}
    elif isinstance(value,(pd.DataFrame,pd.Series)):
        value=encoding._panel_context(value)
    return encoding._sha(encoding._normalize(value))


def correct_one_cell(inputs,*,day=DAY,ticker='GOOG',old_value=0.,new_value=VALUE):
    """Return independent inputs and verify every other typed value is unchanged."""
    if type(old_value) not in (int,float) or type(new_value) not in (int,float):
        raise ValueError('Explicit nonboolean numerical correction required')
    original=deepcopy(inputs)
    updated=deepcopy(inputs)
    stamp=pd.Timestamp(day)
    if ticker not in updated['returns'] or stamp not in updated['returns'].index:
        raise ValueError('Explicit correction cell absent')
    if float(updated['returns'].at[stamp,ticker]).hex()!=float(old_value).hex():
        raise ValueError('Correction expected old cell differs')
    if not np.isfinite(new_value) or new_value<=-1 or new_value==old_value:
        raise ValueError('Finite distinct valid corrected return required')
    updated['returns'].at[stamp,ticker]=new_value
    restored=deepcopy(updated);restored['returns'].at[stamp,ticker]=old_value
    if typed_digest(restored)!=typed_digest(original) or typed_digest(inputs)!=typed_digest(original):
        raise ValueError('Correction changed other input cells or mutated original')
    return updated


def verify_record_invariants(before,after,*,corrected_ticker='GOOG'):
    if len(before)!=len(after):raise ValueError('Original complete record denominator changed')
    for old,new in zip(before,after):
        if set(old)!=set(new):raise ValueError('Record schema changed')
        for field in old:
            if field!='fractional_metrics' and old[field]!=new[field]:
                raise ValueError('Non-return record field changed: '+field)
        a=old['fractional_metrics'];b=new['fractional_metrics']
        if set(a)!=set(b):raise ValueError('Metric schema changed')
        allowed=(ALLOWED_METRICS if corrected_ticker in old['tickers'].split(';') else
                 {key for key in ALLOWED_METRICS if key.startswith('paired_')})
        if any(a[key]!=b[key] for key in a if key not in allowed):
            raise ValueError('Risk, turnover or initial fee semantics changed')


def runtime():
    return dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,scipy=encoding.scipy.__version__)


def window_coverage(inputs):
    contract=inputs['contract'];calendar=inputs['returns'].index
    return [dict(start_position=start,first=str(calendar[start].date()),
        last=str(calendar[start+contract['window_days']-1].date()),
        contains_corrected_cell=pd.Timestamp(DAY) in calendar[start:start+contract['window_days']])
        for start in range(contract['fit_days'],len(calendar)-contract['window_days']+1,contract['step_days'])]


def prepare_date(selection_date):
    old_report._check_sources(LOADED)
    inventory=bound(INVENTORY,INVENTORY_SHA)
    if (inventory['date_count']!=15 or sorted(row['coordinate']['selection_date'] for row in inventory['summaries'])!=list(DATES)
            or inventory['record_count']!=351255):raise ValueError('Complete original 15-date inventory required')
    descriptor,=[row for row in inventory['summaries'] if row['coordinate']['selection_date']==selection_date]
    summary=bound(descriptor['path'],descriptor['sha256'])
    coordinate=descriptor['coordinate']
    if any(summary['expected_date'][key]!=value for key,value in coordinate.items()):raise ValueError('Summary coordinate mismatch')
    path,digest=next_reference=next(iter([(path,digest) for path,digest in summary['source_hashes'].items()
        if Path(path).name=='equal_base_'+selection_date.replace('-','')+'_20260911.json']), (None,None))
    references=[(p,s) for p,s in summary['source_hashes'].items() if Path(p).name.startswith('equal_base_')]
    if len(references)!=1 or references[0]!=next_reference:raise ValueError('Unique dated equal report required')
    previous=old_report.load_report(path,expected_sha256=digest)
    prepared=preparation.prepare_equal_base_date(**coordinate)
    if (previous['coordinate']!=coordinate or previous['definitions']!=[list(combo) for combo in prepared['combinations']]
            or previous['training_semantics']!=prepared['training_semantics'] or previous['input_summary']!=prepared['summary']):
        raise ValueError('Original equal input/definition/semantics denominator differs')
    correction=bound(CORRECTION,CORRECTION_SHA)
    event,=[row for row in correction['known_split_day_return_errors'] if row['ticker']=='GOOG' and row['session']==DAY]
    raw=bound(event['raw_response_path'],event['raw_response_sha256'])
    chart,=raw['chart']['result'];quotes,=chart['indicators']['quote']
    days=[datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat() for t in chart['timestamp']]
    index=days.index(DAY)
    value=quotes['close'][index]/quotes['close'][index-1]-1
    if (days[index-1]!=event['previous_session'] or value!=VALUE
            or event['provider_split_adjusted_price_return']!=value or event['legacy_root_return']!=0.):
        raise ValueError('Corrected cell does not reproduce bound actual quote evidence')
    inputs=prepared['inputs'];updated=correct_one_cell(inputs)
    indexed=bound(preparation.INDEX,preparation.INDEX_SHA)
    original_context=next(row['context_sha256'] for row in indexed['coordinates']
        if row['context_sha256'] and all(row[key]==value for key,value in coordinate.items()))
    context_path=ROOT/'data/cache/research/ndx_joint_weight_runs_v3'/original_context/'context.json'
    if prepared['source_hashes'].get(str(context_path))!=original_context:
        raise ValueError('Exact original input context not bound')
    context=bound(context_path,original_context)
    if context['runtime']!=runtime():raise ValueError('Runtime differs from original context; separate migration review required')
    windows=window_coverage(inputs)
    affected=any(row['contains_corrected_cell'] for row in windows)
    if affected!=(selection_date in DATES[:10]):raise ValueError('Actual forward cell coverage differs from isolated scope')
    sources=dict(LOADED)
    for mapping in (previous['source_hashes'],prepared['source_hashes'],correction['source_hashes'],
            {str(INVENTORY):INVENTORY_SHA,str(CORRECTION):CORRECTION_SHA,str(Path(path).resolve()):digest,
             str(Path(descriptor['path']).resolve()):descriptor['sha256']}):old_report._merge(sources,mapping)
    old_report._check_sources(sources)
    return dict(coordinate=coordinate,previous=previous,inputs=inputs,corrected_inputs=updated,
        combinations=prepared['combinations'],source_hashes=sources,
        audit=dict(old_report_path=path,old_report_sha256=digest,correction_path=str(CORRECTION),
            original_context_path=str(context_path),original_context_sha256=original_context,
            original_context_runtime=context['runtime'],runtime_exactly_matches_original_context=True,
            correction_sha256=CORRECTION_SHA,cell=dict(ticker='GOOG',session=DAY,old_value=0.,new_value=value),
            original_input_sha256=typed_digest(inputs),corrected_input_sha256=typed_digest(updated),
            unchanged_other_input_sha256={key:typed_digest(item) for key,item in inputs.items() if key!='returns'},
            original_training_semantics=previous['training_semantics'],window_coverage=windows,
            forward_affected=affected,record_count=len(previous['evaluation']['records']),
            only_one_input_cell_changed=True,old_input_mutated=False))


def evaluate_prepared(prepared):
    sources=prepared['source_hashes'];old_report._check_sources(sources)
    windows=window_coverage(prepared['inputs'])
    affected=any(row['contains_corrected_cell'] for row in windows)
    if (windows!=prepared['audit']['window_coverage'] or affected!=prepared['audit']['forward_affected']
            or affected!=(prepared['coordinate']['selection_date'] in DATES[:10])):
        raise ValueError('Prepared forward coverage assertion differs from actual input windows')
    if (prepared['audit']['record_count']!=len(prepared['previous']['evaluation']['records'])
            or len(prepared['combinations'])!=prepared['audit']['record_count']):
        raise ValueError('Prepared complete record denominator changed')
    if runtime()!=prepared['audit']['original_context_runtime']:
        raise ValueError('Runtime differs from original context')
    previous=old_report.load_report(prepared['audit']['old_report_path'],expected_sha256=prepared['audit']['old_report_sha256'])
    if previous!=prepared['previous']:raise ValueError('Prepared original report differs from bound source')
    if (typed_digest(prepared['inputs'])!=prepared['audit']['original_input_sha256']
            or typed_digest(prepared['corrected_inputs'])!=prepared['audit']['corrected_input_sha256']
            or typed_digest(correct_one_cell(prepared['inputs']))!=typed_digest(prepared['corrected_inputs'])
            or [list(combo) for combo in prepared['combinations']]!=prepared['previous']['definitions']):
        raise ValueError('Prepared one-cell input or complete definitions mutated')
    raise ValueError('Single GOOG execution superseded; use evidenced multi-cell delta entry')
    if prepared['audit']['forward_affected']:
        inputs=prepared['corrected_inputs']
        evaluation=evaluator.evaluate_equal_weight_fractional_batch(combinations=prepared['combinations'],
            **{key:inputs[key] for key in ('universe','returns','target_returns','incumbent_weights','contract')})
        verify_record_invariants(prepared['previous']['evaluation']['records'],evaluation['records'])
        for key,value in prepared['previous']['evaluation'].items():
            if key not in ('records','source_hashes') and evaluation[key]!=value:raise ValueError('Evaluation metadata changed')
        old_report._merge(sources,evaluation['source_hashes'])
        mode='REEVALUATED_CHANGED_NUMERICAL_INPUT'
    else:
        evaluation=None;mode='OLD_EQUAL_RECORDS_REFERENCED_FORWARD_INPUT_UNCHANGED'
    old_report._check_sources(sources)
    return dict(schema='ndx_goog_equal_single_cell_delta_v1',coordinate=prepared['coordinate'],
        audit=prepared['audit'],evaluation=evaluation,mode=mode,source_hashes=sources,
        original_equal_record_denominator=prepared['audit']['record_count'],
        corrected_inputs={key:encoding._panel_context(item) for key,item in prepared['corrected_inputs'].items()},
        runtime=runtime(),platform_diagnostic=platform.platform(),
        complete_date_checkpoint=True,original_outputs_overwritten=False,
        correction_scope='ONE_GOOG_RETURN_CELL_NOT_GENERAL_PROVIDER_OR_NEW_NDX_SCOPE_REPAIR',
        historical_numerical_delta_performed=evaluation is not None,whole_lot_execution_performed=False,
        new_universe_admission=False,ranking_or_promotion_performed=False,point_in_time_verified=False,promotion_allowed=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection-date',choices=DATES,required=True)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    if args.execute:raise ValueError('Single GOOG execution superseded; use evidenced multi-cell delta entry')
    output=ROOT/'data/cache/research/goog_equal_single_cell_delta_20260912_v1'/('equal_delta_'+args.selection_date.replace('-','')+'.json')
    if args.execute and output.exists():raise FileExistsError('Completed date exists; verify rather than repeat: '+str(output))
    prepared=prepare_date(args.selection_date)
    if not args.execute:
        print(json.dumps(prepared['audit'],sort_keys=True));return
    report=evaluate_prepared(prepared)
    raw=(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    old_report._check_sources(report['source_hashes']);output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as stream:stream.write(raw)
    if output.read_bytes()!=raw:raise ValueError('Create-only output readback differs')
    old_report._check_sources(report['source_hashes'])
    print(json.dumps(dict(path=str(output),sha256=hashlib.sha256(raw).hexdigest(),mode=report['mode'])))


if __name__=='__main__':main()
