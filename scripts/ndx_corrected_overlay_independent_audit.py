"""Read-only task/metric lineage audit, without importing overlay or evaluators."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'data/cache/research/three_cell_corrected_cohort_overlay_20260912_v1'


def sha(raw):return hashlib.sha256(raw).hexdigest()
def digest(value):return sha(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
def decode(value):
    if not isinstance(value,dict):return value
    if set(value)=={'mapping'}:return {k:decode(v) for k,v in value['mapping'].items()}
    if set(value)=={'float_hex'}:return float.fromhex(value['float_hex'])
    if set(value)=={'timestamp'}:return value['timestamp']
    if set(value)=={'sequence_type','items'}:return [decode(v) for v in value['items']]
    raise ValueError('Unknown original checkpoint encoding')
def clean(value):return {k:v for k,v in value.items() if not k.startswith('whole_lot_') and k not in ('declared_constraints_passed','constraint_failure_reasons','projection_reconstruction_audit')}


def audit(date,expected_sha):
    path=FOLDER/('overlay_'+date.replace('-','')+'.json');raw=path.read_bytes()
    if sha(raw)!=expected_sha:raise ValueError('External overlay SHA mismatch')
    result=json.loads(raw);sources=dict(result['source_hashes']);sources[str(path)]=expected_sha;cache={}
    for p,h in sources.items():
        if sha(Path(p).read_bytes())!=h:raise ValueError('Source drift')
    def read(p):
        if p not in cache:
            payload=Path(p).read_bytes()
            if sha(payload)!=sources[p]:raise ValueError('Lineage source differs')
            cache[p]=json.loads(payload)
        return cache[p]
    classification_path=next(p for p in sources if Path(p).name=='three_cell_saved_dependency_20260912.json')
    classified=read(classification_path)
    groups={key.split('|',1)[1]:rows for key,rows in classified['buckets'].items() if key.startswith(date+'|')}
    by_task={row['task']['job_id']:(origin_category,row) for origin_category,rows in groups.items() if not origin_category.startswith('EQUAL_WEIGHT_BASE|') for row in rows}
    equal_by_index={row['row_index']:(category,row) for category,rows in groups.items() if category.startswith('EQUAL_WEIGHT_BASE|') for row in rows}
    if len(result['records'])!=sum(len(rows) for rows in groups.values()) or digest(result['records'])!=result['records_sha256']:
        raise ValueError('Complete task denominator/records SHA mismatch')
    seen=set();equal_seen=set();counts=Counter();patches=0
    for record in result['records']:
        task=record['task'];origin=record['origin'];lineage=record['lineage'];key=task['job_id']
        if key in seen or record['eligibility'] is not None or record['promotion_allowed'] is not False:
            raise ValueError('Duplicate task or false admission')
        seen.add(key);counts[origin+'|'+record['status']]+=1
        if origin=='EQUAL_WEIGHT_BASE':
            index=lineage['old_row_index'];equal_seen.add(index);category,ref=equal_by_index[index]
            old_report=read(lineage['old_report_path']);old=old_report['evaluation']['records'][index]
            corrected=read(lineage['corrected_report_path'])
            if corrected['evaluation'] is None:
                if not category.endswith('|NO_DEPENDENCY') or corrected['mode']!='OLD_EQUAL_RECORDS_REFERENCED_ALL_FORWARD_INPUTS_UNCHANGED':raise ValueError('Stale equal reuse')
                selected=old
            else:selected=corrected['evaluation']['records'][index]
            if old['risk_liquidity_metrics']!=selected['risk_liquidity_metrics']:raise ValueError('Equal risk changed')
            expected=clean(dict(selected['fractional_metrics'],**selected['risk_liquidity_metrics'],**{k:old[k] for k in ('tickers','holding_count','weight_spec')}))
            for k in ('tickers','holding_count','weight_spec'):
                if task[k]!=old[k] or selected[k]!=old[k]:raise ValueError('Equal task definition differs')
            if task['training_semantics_sha256']!=old_report['training_semantics']['training_semantics_sha256']:raise ValueError('Equal original semantics differ')
        else:
            category,ref=by_task[key]
            if ref['task']!=task or ref['checkpoint_path']!=lineage['original_checkpoint_path'] or ref['checkpoint_sha256']!=lineage['original_checkpoint_sha256']:
                raise ValueError('Saved task lineage mismatch')
            old=decode(read(lineage['original_checkpoint_path'])['result']);old=old['result'] if origin=='NON_EQUAL_BASE' else old
            expected=clean(old)
            if category.endswith('|NO_DEPENDENCY'):
                if record['overlay_mode']!='ORIGINAL_UNCHANGED':raise ValueError('Nondependent original not referenced')
            elif origin=='NON_EQUAL_BASE' and category.endswith('|PAIRED_ONLY_NO_REFIT'):
                corrected=read(lineage['corrected_checkpoint_path'])['result'];patch=corrected['corrected']['metrics']
                if corrected['task']!=task or len(patch)!=20:raise ValueError('Twenty-metric task patch differs')
                expected.update(patch);patches+=1
            else:
                expected=None
                if record['status']!='PENDING_NUMERICAL_DELTA' or record['overlay_mode']!='PENDING':raise ValueError('Pending task incorrectly available')
        if record['result']!=expected:raise ValueError('Result differs from exact corrected/original source or pending has old metrics')
    if equal_seen!=set(equal_by_index):raise ValueError('Equal row denominator differs')
    available=sum(v for k,v in counts.items() if k.endswith('|AVAILABLE'))
    if available!=result['available_count'] or len(seen)-available!=result['pending_count'] or result['winner'] is not None or result['point_in_time_verified'] is not False:
        raise ValueError('Summary boundary differs')
    sources[str(Path(__file__).resolve())]=sha(Path(__file__).read_bytes())
    for p,h in sources.items():
        if sha(Path(p).read_bytes())!=h:raise ValueError('Source changed after audit')
    return dict(schema='ndx_corrected_overlay_independent_audit_v1',source_hashes=sources,date=date,
        original_count=len(seen),available=available,pending=len(seen)-available,origin_status_counts=dict(counts),
        exact_twenty_metric_patches=patches,all_result_sources_reconstructed_exact=True,
        pending_metrics_absent=True,eligibility_absent=True,training_performed=False,promotion_allowed=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--date',required=True);parser.add_argument('--sha256',required=True);args=parser.parse_args()
    report=audit(args.date,args.sha256);path=FOLDER/('independent_audit_'+args.date.replace('-','')+'.json')
    with path.open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2,sort_keys=True);stream.write('\n')
    print(json.dumps(dict(path=str(path),sha256=sha(path.read_bytes()),available=report['available'],pending=report['pending'])))
