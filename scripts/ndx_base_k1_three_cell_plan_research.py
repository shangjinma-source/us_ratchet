"""Separate ninety constant-single-name BASE tasks; no fitting or evaluation."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_non_equal_base_runner as runner
from scripts.ndx_joint_weight_verify import _restore


def run():
    path=ROOT/'data/cache/research/root_return_semantics_probe_20260912_v1/three_cell_saved_dependency_20260912.json'
    expected='ae3fed1689457034fbe51227de1f9202a3b9602e6e0a95afa3657fdae2771da0'
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('Hard plan differs')
    plan=json.loads(raw);sources={str(path):expected}
    source=Path(__file__).resolve();sources[str(source)]=hashlib.sha256(source.read_bytes()).hexdigest()
    sources.update(runner.evaluator._sources())
    rows=[];counts=Counter()
    for key,records in plan['buckets'].items():
        if not key.endswith('|NON_EQUAL_BASE|SELECTED_INPUT_CHANGED'):continue
        date=key.split('|')[0]
        for record in records:
            task=record['task']
            if task['holding_count']!=1:continue
            raw=Path(record['checkpoint_path']).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=record['checkpoint_sha256']:raise ValueError('Original checkpoint differs')
            checkpoint=json.loads(raw);saved=_restore(checkpoint['result'])
            runner._validate_result(saved,task,runner.evaluator._sources())
            if checkpoint['task']!=task:raise ValueError('Original task differs')
            for window in saved['historical_window_weights']:
                if window['weights']!={task['tickers']:1.}:raise ValueError('Original single-name weight is not one')
            errors=plan['masks_by_date'][date]
            selected,=[e for e in errors if e['ticker']==task['tickers']]
            category=('OWN_FORWARD_REEVALUATION_NO_FIT' if selected['in_forward'] else
                'INCUMBENT_PAIRED_ONLY_NO_FIT' if any(e['incumbent_positive'] and e['in_forward'] for e in errors) else
                'NO_NUMERICAL_DEPENDENCY')
            counts[category]+=1;sources[record['checkpoint_path']]=record['checkpoint_sha256']
            rows.append(dict(**record,category=category,original_window_count=len(saved['historical_window_weights']),
                mathematical_branch='K1_RETURNS_UNIT_WEIGHT_BEFORE_COVARIANCE_ANCHOR_PROJECTION'))
    if len(rows)!=90 or len({r['task']['job_id'] for r in rows})!=90 or dict(counts)!={
        'OWN_FORWARD_REEVALUATION_NO_FIT':40,'INCUMBENT_PAIRED_ONLY_NO_FIT':20,'NO_NUMERICAL_DEPENDENCY':30}:
        raise ValueError('Exact independent ninety-task denominator differs')
    runner._verify_sources(sources)
    return dict(schema='ndx_base_k1_three_cell_plan_v1',source_hashes=sources,planned=90,counts=dict(counts),tasks=rows,
        separate_from_existing_2444_batch=True,original_classification_artifact_modified=False,
        training_performed=False,economic_metrics_recomputed=False,original_declared_risk_failures_waived=False,
        point_in_time_verified=False,promotion_allowed=False)


if __name__=='__main__':
    report=run();path=ROOT/'data/cache/research/root_return_semantics_probe_20260912_v1/base_k1_three_cell_plan_20260912.json'
    raw=(json.dumps(report,sort_keys=True,indent=2)+'\n').encode()
    with path.open('xb') as stream:stream.write(raw)
    runner._verify_sources(report['source_hashes'])
    print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest(),planned=report['planned'],counts=report['counts'])))
