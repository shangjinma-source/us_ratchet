"""One isolated equal-weight delta for three evidenced split-day return cells."""
from copy import deepcopy
from datetime import datetime
import argparse
import hashlib
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_goog_equal_single_cell_delta_research as helper
from scripts import ndx_joint_weight_verify as restore

SOURCE=Path(__file__).resolve()
LOADED={str(SOURCE):hashlib.sha256(SOURCE.read_bytes()).hexdigest(),**helper.LOADED}
LOADED[str(Path(restore.__file__).resolve())]=hashlib.sha256(Path(restore.__file__).read_bytes()).hexdigest()
ADDITIONAL=ROOT/'data/cache/research/legacy_pool_additional_split_probe_20260912_v1/report.json'
ADDITIONAL_SHA='64e6c86a9ad8045dcb925990c04a7d00c8480cdec2e922ef215e9ed839acd850'
CELLS=(dict(ticker='GOOG',session='2022-07-18',old_value=0.,new_value=helper.VALUE),
       dict(ticker='GOOGL',session='2022-07-18',old_value=0.,new_value=-0.024580059928059006),
       dict(ticker='FTNT',session='2022-06-23',old_value=0.,new_value=0.019968386675822902))


def apply_cells(inputs,cells):
    if not cells or len({(row['ticker'],row['session']) for row in cells})!=len(cells):
        raise ValueError('Explicit unique correction cells required')
    updated=deepcopy(inputs)
    for cell in cells:
        updated=helper.correct_one_cell(updated,day=cell['session'],ticker=cell['ticker'],
            old_value=cell['old_value'],new_value=cell['new_value'])
    restored=deepcopy(updated)
    for cell in cells:restored['returns'].at[pd.Timestamp(cell['session']),cell['ticker']]=cell['old_value']
    if helper.typed_digest(restored)!=helper.typed_digest(inputs):raise ValueError('Unlisted input values changed')
    return updated


def coverage(inputs,cells):
    calendar=inputs['returns'].index;contract=inputs['contract']
    output=[]
    for cell in cells:
        stamp=pd.Timestamp(cell['session'])
        windows=[dict(start_position=start,first=str(calendar[start].date()),
            last=str(calendar[start+contract['window_days']-1].date()),
            in_fit=stamp in calendar[start-contract['fit_days']:start],
            in_forward=stamp in calendar[start:start+contract['window_days']])
            for start in range(contract['fit_days'],len(calendar)-contract['window_days']+1,contract['step_days'])]
        output.append(dict(ticker=cell['ticker'],session=cell['session'],windows=windows,
            incumbent_weight=inputs['incumbent_weights'].get(cell['ticker'],0.),
            forward_affected=any(row['in_forward'] for row in windows)))
    return output


def prepare_date(selection_date):
    helper.old_report._check_sources(LOADED)
    prepared=helper.prepare_date(selection_date)
    additional=helper.bound(ADDITIONAL,ADDITIONAL_SHA)
    sources=prepared['source_hashes']
    for mapping in (LOADED,additional['source_hashes'],{str(ADDITIONAL):ADDITIONAL_SHA}):helper.old_report._merge(sources,mapping)
    for cell in CELLS[1:]:
        event,=[row for row in additional['observed_split_events'] if (row['ticker'],row['session'])==(cell['ticker'],cell['session'])]
        raw=helper.bound(event['raw_path'],event['raw_sha256'])
        chart,=raw['chart']['result'];quotes,=chart['indicators']['quote']
        days=[datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat() for t in chart['timestamp']]
        index=days.index(cell['session'])
        actual=quotes['close'][index]/quotes['close'][index-1]-1
        if (actual!=cell['new_value'] or event['provider_split_only_price_return']!=actual
                or event['old_root_return']!=cell['old_value'] or days[index-1]!=event['previous_session']):
            raise ValueError('Additional correction not reproduced from bound raw quote')
    updated=apply_cells(prepared['inputs'],CELLS)
    windows=coverage(prepared['inputs'],CELLS)
    if ([row['ticker'] for row in windows if row['forward_affected']]
            !=(['GOOG','GOOGL'] if selection_date in helper.DATES[:10] else [])):
        raise ValueError('Actual multi-cell forward coverage differs from bounded scope')
    audit=prepared['audit']
    audit.pop('cell');audit.pop('only_one_input_cell_changed');audit.pop('window_coverage')
    audit.update(cells=deepcopy(CELLS),cell_window_coverage=windows,
        corrected_input_sha256=helper.typed_digest(updated),exactly_three_declared_input_cells_changed=True,
        additional_evidence_path=str(ADDITIONAL),additional_evidence_sha256=ADDITIONAL_SHA,
        forward_affected=any(row['forward_affected'] for row in windows),
        additional_probe_receipt_metadata=deepcopy(additional['probes']),
        missing_original_receipt_timestamps_remain_unknown=True)
    prepared['corrected_inputs']=updated
    helper.old_report._check_sources(sources)
    return prepared


def validate_prepared(prepared):
    helper.old_report._check_sources(prepared['source_hashes'])
    audit=prepared['audit'];inputs=prepared['inputs']
    coordinate=prepared['coordinate']
    inventory=helper.bound(helper.INVENTORY,helper.INVENTORY_SHA)
    descriptor,=[row for row in inventory['summaries'] if row['coordinate']==coordinate]
    summary=helper.bound(descriptor['path'],descriptor['sha256'])
    report_path,report_sha=next(iter([(path,digest) for path,digest in summary['source_hashes'].items()
        if Path(path).name=='equal_base_'+coordinate['selection_date'].replace('-','')+'_20260911.json']), (None,None))
    if (audit['old_report_path']!=report_path or audit['old_report_sha256']!=report_sha
            or prepared['previous']['coordinate']!=coordinate):
        raise ValueError('Prepared coordinate or old report differs from hard inventory')
    index=helper.bound(helper.preparation.INDEX,helper.preparation.INDEX_SHA)
    context_sha=next(row['context_sha256'] for row in index['coordinates']
        if row['context_sha256'] and all(row[key]==value for key,value in coordinate.items()))
    context_path=ROOT/'data/cache/research/ndx_joint_weight_runs_v3'/context_sha/'context.json'
    if (audit['original_context_sha256']!=context_sha or audit['original_context_path']!=str(context_path)
            or audit['correction_path']!=str(helper.CORRECTION) or audit['correction_sha256']!=helper.CORRECTION_SHA
            or audit['additional_evidence_path']!=str(ADDITIONAL) or audit['additional_evidence_sha256']!=ADDITIONAL_SHA):
        raise ValueError('Prepared context or correction differs from hard source bindings')
    required={**LOADED,str(helper.INVENTORY):helper.INVENTORY_SHA,str(ADDITIONAL):ADDITIONAL_SHA,
        str(helper.CORRECTION):helper.CORRECTION_SHA,str(helper.preparation.INDEX):helper.preparation.INDEX_SHA,
        str(Path(descriptor['path']).resolve()):descriptor['sha256'],str(Path(report_path).resolve()):report_sha,
        str(context_path):context_sha}
    if any(prepared['source_hashes'].get(path)!=digest for path,digest in required.items()):
        raise ValueError('Required hard source closure missing or changed')
    if audit['cells']!=list(CELLS) and audit['cells']!=CELLS:raise ValueError('Correction set changed')
    windows=coverage(inputs,CELLS);affected=any(row['forward_affected'] for row in windows)
    if (windows!=audit['cell_window_coverage'] or affected!=audit['forward_affected']
            or affected!=(prepared['coordinate']['selection_date'] in helper.DATES[:10])):
        raise ValueError('Prepared forward coverage differs from actual windows')
    previous=helper.old_report.load_report(audit['old_report_path'],expected_sha256=audit['old_report_sha256'])
    if previous!=prepared['previous']:raise ValueError('Prepared original report differs from bound source')
    context=helper.bound(audit['original_context_path'],audit['original_context_sha256'])
    if any(any(task[key]!=value for key,value in coordinate.items()) for task in context['tasks']):
        raise ValueError('Original context task coordinate differs')
    restored={key:restore._restore_input(value)
              for key,value in context['prepared_inputs'].items()}
    if helper.typed_digest(restored)!=helper.typed_digest(inputs):raise ValueError('Prepared input differs from original context')
    if context['runtime']!=helper.runtime() or audit['original_context_runtime']!=context['runtime']:
        raise ValueError('Runtime differs from bound original context')
    if (helper.typed_digest(inputs)!=audit['original_input_sha256']
            or helper.typed_digest(apply_cells(inputs,CELLS))!=helper.typed_digest(prepared['corrected_inputs'])
            or helper.typed_digest(prepared['corrected_inputs'])!=audit['corrected_input_sha256']):
        raise ValueError('Prepared declared-cell correction mutated')
    if ([list(combo) for combo in prepared['combinations']]!=previous['definitions']
            or audit['record_count']!=len(previous['evaluation']['records'])
            or audit['record_count']!=len(prepared['combinations'])):
        raise ValueError('Original complete definition denominator changed')
    return windows


def verify_records(before,after,windows):
    candidates={row['ticker'] for row in windows if row['forward_affected']}
    if len(before)!=len(after):raise ValueError('Original complete record denominator changed')
    for old,new in zip(before,after):
        # FTNT is fit-only in every equal-weight window and cannot alter candidate metrics.
        affected=next(iter(candidates & set(old['tickers'].split(';'))),'__NO_FORWARD_CANDIDATE__')
        helper.verify_record_invariants([old],[new],corrected_ticker=affected)


def evaluate_prepared(prepared):
    windows=validate_prepared(prepared)
    if any(row['forward_affected'] for row in windows):
        inputs=prepared['corrected_inputs']
        evaluation=helper.evaluator.evaluate_equal_weight_fractional_batch(combinations=prepared['combinations'],
            **{key:inputs[key] for key in ('universe','returns','target_returns','incumbent_weights','contract')})
        verify_records(prepared['previous']['evaluation']['records'],evaluation['records'],windows)
        for key,value in prepared['previous']['evaluation'].items():
            if key not in ('records','source_hashes') and evaluation[key]!=value:raise ValueError('Evaluation metadata changed')
        helper.old_report._merge(prepared['source_hashes'],evaluation['source_hashes'])
        mode='REEVALUATED_THREE_DECLARED_CELL_INPUT'
    else:evaluation=None;mode='OLD_EQUAL_RECORDS_REFERENCED_ALL_FORWARD_INPUTS_UNCHANGED'
    helper.old_report._check_sources(prepared['source_hashes'])
    return dict(schema='ndx_evidenced_split_equal_delta_v1',coordinate=prepared['coordinate'],audit=prepared['audit'],
        evaluation=evaluation,mode=mode,source_hashes=prepared['source_hashes'],runtime=helper.runtime(),
        corrected_inputs={key:helper.encoding._panel_context(value) for key,value in prepared['corrected_inputs'].items()},
        original_equal_record_denominator=prepared['audit']['record_count'],complete_date_checkpoint=True,
        correction_scope='THREE_EVIDENCED_PRICE_RETURN_CELLS_CONDITIONAL_RETROSPECTIVE_NUMERICAL_DELTA',
        full_provider_adjustment_repair_verified=False,full_legacy_pool_split_completeness_verified=False,
        missing_receipt_timestamps_inferred=False,original_outputs_overwritten=False,
        historical_numerical_delta_performed=evaluation is not None,whole_lot_execution_performed=False,
        new_ndx_scope_admitted=False,ranking_or_promotion_performed=False,point_in_time_verified=False,promotion_allowed=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection-date',choices=helper.DATES,required=True)
    parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    output=ROOT/'data/cache/research/evidenced_split_equal_delta_20260912_v1'/('equal_delta_'+args.selection_date.replace('-','')+'.json')
    if args.execute and output.exists():raise FileExistsError('Completed date exists; verify rather than repeat: '+str(output))
    prepared=prepare_date(args.selection_date)
    if not args.execute:
        validate_prepared(prepared);print(json.dumps(prepared['audit'],sort_keys=True));return
    report=evaluate_prepared(prepared)
    raw=(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    helper.old_report._check_sources(report['source_hashes']);output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as stream:stream.write(raw)
    if output.read_bytes()!=raw:raise ValueError('Created date checkpoint readback differs')
    helper.old_report._check_sources(report['source_hashes'])
    print(json.dumps(dict(path=str(output),sha256=hashlib.sha256(raw).hexdigest(),mode=report['mode'])))


if __name__=='__main__':main()
