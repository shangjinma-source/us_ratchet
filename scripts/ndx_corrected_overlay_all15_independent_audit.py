"""Audit externally sealed overlays; never generate overlays or fit portfolios."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_corrected_overlay_independent_audit as oracle


def main():
    folder=oracle.FOLDER
    index_path=folder/'root_execution_summary_sha_index_20260912.json'
    index_raw=index_path.read_bytes();index_sha='2f973827ad5140d3bb5262a094e4a4a50912f86b2e1ca595ab932606d3189890'
    if oracle.sha(index_raw)!=index_sha:raise ValueError('External execution index differs')
    index=json.loads(index_raw)
    expected=['2023-04-03','2023-05-01','2023-06-01','2023-07-03','2023-08-01','2023-09-01','2023-10-02',
              '2023-11-01','2023-12-01','2024-01-02','2024-02-01','2024-03-01','2024-04-01','2024-05-01','2024-06-03']
    if sorted(index)!=expected:raise ValueError('Complete fifteen-date index required')
    sources={str(index_path):index_sha,str(Path(__file__).resolve()):oracle.sha(Path(__file__).read_bytes()),
             str(Path(oracle.__file__).resolve()):oracle.sha(Path(oracle.__file__).read_bytes())}
    dates=[];identifiers=set();total=available=pending=0
    for date in expected:
        entry=index[date];path=folder/('overlay_'+date.replace('-','')+'.json')
        if Path(entry['path']).resolve()!=path.resolve():raise ValueError('Unexpected output coordinate path')
        if date=='2023-04-03':
            audit_path=folder/'independent_audit_20230403.json';raw=audit_path.read_bytes()
            audit_sha='53a576bac79ec3e5168ce22b7f8e4af219eae1a5d35f8e4ce3213d5ef4ab082b'
            if oracle.sha(raw)!=audit_sha:raise ValueError('Prior April independent audit differs')
            audit=json.loads(raw);sources[str(audit_path)]=audit_sha
            if audit['source_hashes'].get(str(path))!=entry['sha256']:raise ValueError('April audit/index lineage differs')
        else:audit=oracle.audit(date,entry['sha256'])
        for p,h in audit['source_hashes'].items():
            if p in sources and sources[p]!=h:raise ValueError('Conflicting shared source')
            sources[p]=h
        raw=path.read_bytes()
        if oracle.sha(raw)!=entry['sha256']:raise ValueError('Overlay changed after audit')
        overlay=json.loads(raw)
        for row in overlay['records']:
            if row['overlay_record_id'] in identifiers:raise ValueError('Repeated global overlay task')
            identifiers.add(row['overlay_record_id'])
            if row['status']=='PENDING_NUMERICAL_DELTA' and row['result'] is not None:raise ValueError('Pending leaked metrics')
        total+=audit['original_count'];available+=audit['available'];pending+=audit['pending']
        dates.append({k:v for k,v in audit.items() if k!='source_hashes'})
        print(json.dumps(dict(date=date,available=audit['available'],pending=audit['pending'],cumulative=total)),flush=True)
    if (total,available,pending,len(identifiers))!=(351255,323809,27446,351255):raise ValueError('Global denominator mismatch')
    for p,h in sources.items():
        if oracle.sha(Path(p).read_bytes())!=h:raise ValueError('Final source drift')
    report=dict(schema='ndx_corrected_overlay_all15_independent_audit_v1',source_hashes=sources,dates=dates,
        date_count=15,original_count=total,available_count=available,pending_count=pending,
        unique_overlay_record_count=len(identifiers),april_prior_independent_audit_referenced=True,
        pending_metrics_absent=True,all_result_lineage_exact=True,all_current_economic_metrics_complete=False,
        original_scope='ORIGINAL_RESEARCHED_SUBPOOL_NOT_FULL_NDX',training_performed=False,selection_performed=False,
        point_in_time_verified=False,promotion_allowed=False)
    output=folder/'independent_all15_audit_20260912.json'
    with output.open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2,sort_keys=True);stream.write('\n')
    print(json.dumps(dict(path=str(output),sha256=oracle.sha(output.read_bytes()),sources=len(sources),available=available,pending=pending)))


if __name__=='__main__':main()
