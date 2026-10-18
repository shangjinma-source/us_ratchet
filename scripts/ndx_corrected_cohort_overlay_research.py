"""Read saved original/corrected records; never fit, rank, or execute portfolios."""
from collections import Counter
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtest import ndx_corrected_cohort_overlay_research as overlay
from scripts.ndx_joint_weight_verify import _restore

SELF=Path(__file__).resolve();LOADED=hashlib.sha256(SELF.read_bytes()).hexdigest()
BASE=ROOT/'data/cache/research'
REFERENCES={
 'classification':(BASE/'root_return_semantics_probe_20260912_v1/three_cell_saved_dependency_20260912.json','ae3fed1689457034fbe51227de1f9202a3b9602e6e0a95afa3657fdae2771da0'),
 'original':(BASE/'dynamic_frozen_v2/combined_summary_inventory_20260912.json','baa74f6447e4663ac13a0b4174ad0fa0cf0d799ce3d35a735c9f25379e24ca09'),
 'equal':(BASE/'evidenced_split_equal_delta_20260912_v1/independent_readback_all15_20260912.json','4ed38cc36316dab2be99d22af21715c1a840c93b901cc0b20a35aa2497211c7b'),
 'base':(BASE/'non_equal_three_cell_recovery_20260912_fast_v3/global_summary.json','4871b5826047f3676b5f0bb133fb1aa9a1df909aef17df7f186253083b28341b')}
OUTPUT=BASE/'three_cell_corrected_cohort_overlay_20260912_v1'


class Reader:
    def __init__(self):
        self.sources={str(SELF):LOADED,str(Path(overlay.__file__).resolve()):hashlib.sha256(Path(overlay.__file__).read_bytes()).hexdigest()}
    def merge(self,mapping):
        for path,sha in mapping.items():
            if path in self.sources and self.sources[path]!=sha:raise ValueError('Source conflict')
            self.sources[path]=sha
    def read(self,path,sha):
        path=Path(path).resolve();raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('External bound source differs')
        self.merge({str(path):sha});return json.loads(raw)
    def verify(self):
        for path,sha in self.sources.items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError('Source changed during overlay')


def load_metadata():
    reader=Reader();documents={name:reader.read(path,sha) for name,(path,sha) in REFERENCES.items()}
    original=documents['original'];classified=documents['classification'];equal=documents['equal'];base=documents['base']
    if original['date_count']!=15 or original['record_count']!=351255 or equal['verified_equal_record_count']!=319473 or equal['verified_date_count']!=15:
        raise ValueError('Complete original/equal denominator required')
    if base['recovered_count']!=2444 or base['reference_only_count']!=1526 or base['excluded_refit_count']!=15578:
        raise ValueError('Exact saved BASE recovery denominator required')
    dates=[]
    for descriptor in original['summaries']:
        date=descriptor['coordinate']['selection_date']
        corrected,=[row for row in equal['dates'] if row['coordinate']==descriptor['coordinate']]
        groups={key.split('|')[1]+'|'+key.split('|')[2]:rows for key,rows in classified['buckets'].items() if key.startswith(date+'|')}
        pending=sum(len(rows) for key,rows in groups.items() if key in ('NON_EQUAL_BASE|SELECTED_INPUT_CHANGED','DELTA|SELECTED_INPUT_CHANGED','DELTA|PAIRED_ONLY_NO_REFIT'))
        expected=descriptor['record_count']
        if sum(len(rows) for rows in groups.values())!=expected:raise ValueError('Classification date denominator differs')
        if corrected['record_count']!=descriptor['counts']['EQUAL_WEIGHT_BASE']['observed']:raise ValueError('Corrected equal count differs')
        dates.append(dict(coordinate=descriptor['coordinate'],planned=expected,available=expected-pending,pending=pending,
            origin_counts={key:value['observed'] for key,value in descriptor['counts'].items()},
            corrected_equal_path=corrected['path'],corrected_equal_sha256=corrected['sha256']))
    if (len({r['coordinate']['selection_date'] for r in dates})!=15 or sum(d['available'] for d in dates)!=323809 or sum(d['pending'] for d in dates)!=27446):
        raise ValueError('Exact overlay availability denominator differs')
    plan=dict(schema='ndx_corrected_cohort_overlay_plan_v1',source_hashes=reader.sources,dates=dates,
        original_count=351255,available_count=323809,pending_count=27446,
        correction_signature=overlay.digest(classified['errors']),errors=classified['errors'],
        plan_only=True,all_current_economic_metrics_complete=False,winner=None,
        scope='ORIGINAL_RESEARCHED_SUBPOOL_NOT_FULL_NDX',training_performed=False,promotion_allowed=False)
    reader.verify();return reader,documents,plan


def clean(metrics):
    return {key:value for key,value in metrics.items() if not key.startswith('whole_lot_') and key not in
        ('declared_constraints_passed','constraint_failure_reasons','projection_reconstruction_audit')}


def run_date(date):
    reader,documents,plan=load_metadata()
    descriptor,=[r for r in documents['original']['summaries'] if r['coordinate']['selection_date']==date]
    coordinate=descriptor['coordinate'];summary=reader.read(descriptor['path'],descriptor['sha256'])
    reader.merge(summary['source_hashes'])
    equal_path,=[p for p in summary['source_hashes'] if Path(p).name.startswith('equal_base_')]
    old_equal=reader.read(equal_path,summary['source_hashes'][equal_path])
    new_descriptor,=[r for r in plan['dates'] if r['coordinate']==coordinate]
    new_equal=reader.read(new_descriptor['corrected_equal_path'],new_descriptor['corrected_equal_sha256'])
    reader.merge(new_equal['source_hashes'])
    if (new_equal['coordinate']!=coordinate or new_equal['audit']['old_report_path']!=equal_path or
        new_equal['audit']['old_report_sha256']!=summary['source_hashes'][equal_path]):raise ValueError('Equal replacement lineage differs')
    new_rows=None if new_equal['evaluation'] is None else new_equal['evaluation']['records']
    if new_rows is not None and len(new_rows)!=len(old_equal['evaluation']['records']):raise ValueError('Equal replacement denominator differs')
    groups={key.split('|')[1]+'|'+key.split('|')[2]:rows for key,rows in documents['classification']['buckets'].items() if key.startswith(date+'|')}
    records=[];actions={};signature=old_equal['training_semantics']['training_semantics_sha256']
    for category in ('SELECTED_INPUT_CHANGED','PAIRED_ONLY_NO_REFIT','NO_DEPENDENCY'):
        for reference in groups.get('EQUAL_WEIGHT_BASE|'+category,[]):
            index=reference['row_index'];row=old_equal['evaluation']['records'][index]
            if reference['report_path']!=equal_path or reference['tickers']!=row['tickers']:raise ValueError('Original equal row coordinate differs')
            task=dict(schema_version='ndx_equal_base_combined_task_v1',**coordinate,
                decision_data_end=old_equal['training_semantics']['payload']['decision_data_end'],training_semantics_sha256=signature,
                tickers=row['tickers'],holding_count=row['holding_count'],weight_spec=row['weight_spec'])
            task['job_id']=overlay.digest(task)
            metrics=dict(row['fractional_metrics'],**row['risk_liquidity_metrics'],
                **{key:task[key] for key in ('tickers','holding_count','weight_spec')})
            records.append(dict(task=task,result=clean(metrics),status='EVALUATED',origin='EQUAL_WEIGHT_BASE'))
            action=dict(task=task,origin='EQUAL_WEIGHT_BASE',lineage=dict(old_report_path=equal_path,old_row_index=index,
                corrected_report_path=new_descriptor['corrected_equal_path'],corrected_report_sha256=new_descriptor['corrected_equal_sha256']))
            if new_rows is None:
                if category!='NO_DEPENDENCY' or new_equal['mode']!='OLD_EQUAL_RECORDS_REFERENCED_ALL_FORWARD_INPUTS_UNCHANGED':
                    raise ValueError('Only unchanged forward records may reference original equal metrics')
                action.update(mode='ORIGINAL_UNCHANGED',evidence='NO_DEPENDENCY_ON_THREE_CELLS')
            else:
                revised=new_rows[index]
                if any(revised[key]!=row[key] for key in ('tickers','holding_count','weight_spec','risk_liquidity_metrics')):
                    raise ValueError('Equal identity/risk fields changed')
                if category=='PAIRED_ONLY_NO_REFIT' and any(revised['fractional_metrics'][key]!=value for key,value in row['fractional_metrics'].items() if key not in overlay.PAIRED_KEYS):
                    raise ValueError('Nondependent equal absolute/fee metrics changed')
                new_metrics=dict(revised['fractional_metrics'],**revised['risk_liquidity_metrics'],
                    **{key:task[key] for key in ('tickers','holding_count','weight_spec')})
                action.update(mode='REPLACED_FULL',metrics=clean(new_metrics))
            actions[task['job_id']]=action
    recovered={}
    fast_summaries=[r for r in documents['base']['date_summaries'] if Path(r['path']).parent.name==date.replace('-','')]
    if fast_summaries:
        fast_descriptor,=fast_summaries;fast=reader.read(fast_descriptor['path'],fast_descriptor['sha256'])
        context_path=Path(fast_descriptor['path']).with_name('context.json');context=reader.read(context_path,fast['context_sha256'])
        reader.merge(context['source_hashes'])
        for item in fast['outputs']:
            checkpoint=reader.read(item['path'],item['sha256'])
            if checkpoint['task']['job_id']!=item['job_id'] or checkpoint['context_sha256']!=fast['context_sha256']:
                raise ValueError('Corrected BASE checkpoint context differs')
            recovered[item['job_id']]=(checkpoint['result'],item)
    expected_recovered={r['task']['job_id'] for r in groups.get('NON_EQUAL_BASE|PAIRED_ONLY_NO_REFIT',[])}
    if set(recovered)!=expected_recovered:raise ValueError('Exact available BASE corrected task set differs')
    for origin in ('NON_EQUAL_BASE','DELTA'):
        for category in ('SELECTED_INPUT_CHANGED','PAIRED_ONLY_NO_REFIT','NO_DEPENDENCY'):
            for reference in groups.get(origin+'|'+category,[]):
                checkpoint=reader.read(reference['checkpoint_path'],reference['checkpoint_sha256']);task=reference['task']
                if checkpoint['task']!=task or checkpoint['status']!='EVALUATED':raise ValueError('Original saved task differs')
                restored=_restore(checkpoint['result']);metrics=restored['result'] if origin=='NON_EQUAL_BASE' else restored
                records.append(dict(task=task,result=clean(metrics),status='EVALUATED',origin=origin))
                action=dict(task=task,origin=origin,lineage=dict(original_checkpoint_path=reference['checkpoint_path'],
                    original_checkpoint_sha256=reference['checkpoint_sha256']))
                if category=='NO_DEPENDENCY':action.update(mode='ORIGINAL_UNCHANGED',evidence='NO_DEPENDENCY_ON_THREE_CELLS')
                elif origin=='NON_EQUAL_BASE' and category=='PAIRED_ONLY_NO_REFIT':
                    restored_new,item=recovered[task['job_id']]
                    if (restored_new['task']!=task or restored_new['original_checkpoint_path']!=reference['checkpoint_path'] or
                        restored_new['original_checkpoint_sha256']!=reference['checkpoint_sha256'] or
                        restored_new['dependency_fields_changed']!=['incumbent_forward_returns']):raise ValueError('BASE numerical patch lineage differs')
                    action.update(mode='SAVED_WINDOW_ECONOMIC_PATCH',patch=restored_new['corrected']['metrics'])
                    action['lineage'].update(corrected_checkpoint_path=item['path'],corrected_checkpoint_sha256=item['sha256'])
                else:action.update(mode='PENDING',pending_reason='AWAITING_VERSIONED_NUMERICAL_DELTA')
                actions[task['job_id']]=action
    result=overlay.overlay_date(coordinate=coordinate,original_records=records,actions=actions,
        expected_counts=new_descriptor['origin_counts'],correction_signature=plan['correction_signature'])
    if result['available_count']!=new_descriptor['available'] or result['pending_count']!=new_descriptor['pending']:
        raise ValueError('Real overlay and planned complete denominator differ')
    reader.verify();result['source_hashes']=reader.sources
    result['records_sha256']=overlay.digest(result['records']);result['training_performed']=False
    return result


def save_new(path,value):
    raw=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode();path=Path(path)
    if path.exists():raise FileExistsError('Existing overlay must be read, not overwritten')
    path.parent.mkdir(parents=True,exist_ok=True);fd,temp=tempfile.mkstemp(prefix='.publishing-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.link(temp,path)
    finally:Path(temp).unlink(missing_ok=True)
    for source,sha in value['source_hashes'].items():
        if hashlib.sha256(Path(source).read_bytes()).hexdigest()!=sha:raise ValueError('Post-save source drift')
    return dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest())


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--selection-date');options=parser.parse_args()
    if options.selection_date:
        value=run_date(options.selection_date);path=OUTPUT/('overlay_'+options.selection_date.replace('-','')+'.json')
    else:
        _,_,value=load_metadata();path=OUTPUT/'plan.json'
    result=save_new(path,value)
    result.update(available=value['available_count'],pending=value['pending_count'])
    print(json.dumps(result))
