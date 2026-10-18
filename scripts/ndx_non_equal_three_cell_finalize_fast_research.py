"""Read-only finalize externally hashed completed no-fit date summaries."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_non_equal_three_cell_recovery_fast_research as batch
SELF=Path(__file__).resolve()
LOADED=hashlib.sha256(SELF.read_bytes()).hexdigest()


def finalize(*,index_path,index_sha256):
    batch.runner._verify_sources({str(SELF):LOADED})
    plan=batch.load_plan();index=batch.read(index_path,index_sha256)
    dates=sorted({key.split('|')[0] for key in plan['buckets'] if key.endswith('|NON_EQUAL_BASE|PAIRED_ONLY_NO_REFIT')})
    if sorted(index)!=dates:raise ValueError('Complete ten-date external SHA index required')
    sources={str(batch.PLAN):batch.PLAN_SHA,str(Path(index_path).resolve()):index_sha256}
    reports=[];identifiers=set()
    for date in dates:
        result=batch.verify_completed(plan,date,index[date]);reports.append(result)
        report=batch.read(result['path'],result['sha256']);sources[result['path']]=result['sha256']
        context_path=Path(result['path']).with_name('context.json')
        context=batch.read(context_path,report['context_sha256'])
        sources=batch.merge(sources,context['source_hashes'],{str(context_path):report['context_sha256']})
        for row in report['outputs']:
            if row['job_id'] in identifiers:raise ValueError('Repeated recovered task')
            identifiers.add(row['job_id']);sources[row['path']]=row['sha256']
    references=[r for key,rows in plan['buckets'].items() if key.endswith('|NON_EQUAL_BASE|NO_DEPENDENCY') for r in rows]
    excluded=[r for key,rows in plan['buckets'].items() if key.endswith('|NON_EQUAL_BASE|SELECTED_INPUT_CHANGED') for r in rows]
    if len(identifiers)!=2444 or len(references)!=1526 or len(excluded)!=15578:raise ValueError('Global exact denominator differs')
    for row in references+excluded:
        batch.read(row['checkpoint_path'],row['checkpoint_sha256']);sources[row['checkpoint_path']]=row['checkpoint_sha256']
    sources[str(SELF)]=LOADED
    sources[str(batch.SELF)]=batch.LOADED
    report=dict(schema='ndx_three_cell_no_fit_global_summary_fast_v3',source_hashes=sources,date_summaries=reports,
        recovered_count=2444,reference_only_count=1526,excluded_refit_count=15578,
        reference_only=references,excluded_refit=excluded,exact_task_denominator=19548,
        all_non_equal_training_complete=False,fitted=False,finalization_recomputed_metrics=False,promotion_allowed=False)
    path=batch.OUTPUT/'global_summary.json';batch.runner._verify_sources(sources)
    sha=batch.publish(path,report);batch.runner._verify_sources(sources)
    return dict(path=str(path),sha256=sha,recovered_count=2444)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index-path',required=True);parser.add_argument('--index-sha256',required=True)
    options=parser.parse_args()
    print(json.dumps(finalize(index_path=options.index_path,index_sha256=options.index_sha256)))
