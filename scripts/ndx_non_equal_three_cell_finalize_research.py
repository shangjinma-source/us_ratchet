"""Read back all 2444 recovered tasks; retain reference-only and excluded tasks."""
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_non_equal_three_cell_recovery_research as batch


def finalize():
    plan=batch.load_plan();sources={str(batch.PLAN):batch.PLAN_SHA}
    dates=sorted({key.split('|')[0] for key in plan['buckets'] if key.endswith('|NON_EQUAL_BASE|PAIRED_ONLY_NO_REFIT')})
    reports=[];identifiers=set()
    for date in dates:
        # Pure recovery also revalidates every existing task's numerical content; no fits.
        result=batch.run_date(plan,date,execute=True)
        report=batch.read(result['path'],result['sha256']);reports.append(result)
        sources[result['path']]=result['sha256']
        expected={r['task']['job_id'] for r in plan['buckets'][date+'|NON_EQUAL_BASE|PAIRED_ONLY_NO_REFIT']}
        if {r['job_id'] for r in report['outputs']}!=expected:raise ValueError('Date task denominator differs')
        for row in report['outputs']:
            if row['job_id'] in identifiers:raise ValueError('Repeated recovered task')
            identifiers.add(row['job_id']);batch.read(row['path'],row['sha256']);sources[row['path']]=row['sha256']
    references=[r for key,rows in plan['buckets'].items() if key.endswith('|NON_EQUAL_BASE|NO_DEPENDENCY') for r in rows]
    excluded=[r for key,rows in plan['buckets'].items() if key.endswith('|NON_EQUAL_BASE|SELECTED_INPUT_CHANGED') for r in rows]
    if len(identifiers)!=2444 or len(references)!=1526 or len(excluded)!=15578:raise ValueError('Global exact denominator differs')
    for row in references+excluded:
        batch.read(row['checkpoint_path'],row['checkpoint_sha256'])
    self=Path(__file__).resolve();sources[str(self)]=hashlib.sha256(self.read_bytes()).hexdigest()
    sources[str(batch.SELF)]=batch.LOADED
    report=dict(schema='ndx_three_cell_no_fit_global_summary_v2',source_hashes=sources,date_summaries=reports,
        recovered_count=2444,reference_only_count=1526,excluded_refit_count=15578,
        reference_only=references,excluded_refit=excluded,exact_task_denominator=19548,
        all_non_equal_training_complete=False,fitted=False,promotion_allowed=False)
    path=batch.OUTPUT/'global_summary.json';sha=batch.publish(path,report);batch.runner._verify_sources(sources)
    return dict(path=str(path),sha256=sha,recovered_count=2444)


if __name__=='__main__':
    print(json.dumps(finalize()))
