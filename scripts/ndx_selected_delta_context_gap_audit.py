"""Read all selected-change original contexts without evaluating candidates."""
import json
import hashlib
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_delta_three_cell_paired_probe_research as prior
from backtest import ndx_delta_paired_trace_recovery_v2_research as gap


def main():
    classified=prior.original.read(prior.CLASSIFICATION,prior.CLASSIFICATION_SHA)
    inventory=prior.original.read(prior.INVENTORY,prior.INVENTORY_SHA)
    sources=dict(classified['source_hashes'])
    sources=prior.original.merge(sources,{str(prior.CLASSIFICATION):prior.CLASSIFICATION_SHA,str(prior.INVENTORY):prior.INVENTORY_SHA})
    refs={};tasks=set();dates=[]
    for item in inventory['summaries']:
        date=item['coordinate']['selection_date'];rows=classified['buckets'].get(date+'|DELTA|SELECTED_INPUT_CHANGED',[])
        if not rows:continue
        summary=prior.original.read(item['path'],item['sha256'])
        sources=prior.original.merge(sources,summary['source_hashes'],{item['path']:item['sha256']})
        for row in rows:
            ref=prior.task_context_reference(row,sources);path=ref['context_path']
            if path in refs:assert refs[path]['context_sha256']==ref['context_sha256']
            else:refs[path]=dict(**ref,tasks=[])
            identifier=row['task']['job_id'];assert identifier not in tasks;tasks.add(identifier)
            refs[path]['tasks'].append(row['task'])
        dates.append(dict(date=date,tasks=len(rows)))
    assert len(tasks)==11254 and len(refs)==161 and len(dates)==15
    observations=[]
    for path,entry in refs.items():
        context=prior.original.read(path,entry['context_sha256'])
        assert all(task in context['tasks'] for task in entry['tasks'])
        observations.append(dict(context_path=path,context_sha256=entry['context_sha256'],tasks=len(entry['tasks']),
            gaps=gap.validate_historical_evidence(context,sources)))
    sources=prior.original.merge(sources,{str(Path(__file__).resolve()):hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),str(gap.SOURCE):gap.LOADED,str(prior.SELF):prior.LOADED})
    prior.original.original._verify_sources(sources)
    report=dict(schema='ndx_selected_delta_context_gap_audit_v1',source_hashes=sources,task_count=11254,
        context_count=161,dates=dates,observations=observations,historical_fit_performed=False,
        original_historical_provenance_verified=False,point_in_time_verified=False,promotion_allowed=False)
    output=ROOT/'data/cache/research/delta_selected_input_20260912_v1/context_gap_audit.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2,sort_keys=True);stream.write('\n')
    print(json.dumps(dict(path=str(output),sha256=hashlib.sha256(output.read_bytes()).hexdigest(),sources=len(sources))))


if __name__=='__main__':main()
