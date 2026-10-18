"""Read-only full-denominator checkpoint progress, not economic recomputation."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_joint_weight_batch as batch
from scripts.ndx_joint_weight_verify import _restore, _restore_input
from backtest import ndx_joint_weight_runner as runner

RETURN_FIELDS=('return_p50_vs_012922','return_p10_vs_012922',
    'paired_return_p50_vs_incumbent','paired_return_p10_vs_incumbent')
DRAWDOWN_FIELDS=('max_drawdown_p50_vs_012922','max_drawdown_p90_vs_012922',
    'paired_drawdown_cost_p50_vs_incumbent','paired_drawdown_cost_p90_vs_incumbent')
PREFERENCE='AMAT;AVGO;CDNS;GOOG'


def _require(condition,message):
    if not condition:
        raise ValueError(message)


class Snapshot:
    def __init__(self):
        self.files={}
        self.directories={}

    def read(self,path):
        path=Path(path)
        raw=path.read_bytes()
        _require(path not in self.files or self.files[path]==raw,'File changed during observation')
        self.files[path]=raw
        result=json.loads(raw)
        _require(runner._json_bytes(result)==raw,'Noncanonical captured JSON')
        return result

    def directory(self,path):
        path=Path(path)
        names=frozenset(p.name for p in path.glob('*.json'))
        _require(path not in self.directories or self.directories[path]==names,'Directory changed during observation')
        self.directories[path]=names
        return names

    def verify(self):
        for path,raw in self.files.items():
            _require(path.read_bytes()==raw,'File changed during observation')
        for path,names in self.directories.items():
            _require(frozenset(p.name for p in path.glob('*.json'))==names,'Directory changed during observation')


def inspect_plan(plan,*,cli_hash,capture_destination=None):
    snapshot=Snapshot()
    numerical=runner._source_hashes()
    runtime=dict(python=runner.platform.python_version(),numpy=runner.np.__version__,
                 pandas=runner.pd.__version__,scipy=runner.scipy.__version__)
    _require(numerical==runner._LOADED_SOURCE_HASHES,'Numerical source changed since import')
    destination=(Path(capture_destination) if capture_destination is not None else
        batch.BATCH_ROOT/runner._sha(dict(experiment_sha256=plan['experiment_sha256'],cli_sha256=cli_hash)))
    capture_names=snapshot.directory(destination)
    expected_captures={p['child_sha256']+'.json' for p in plan['plans'] if p['tasks']}
    _require(capture_names<=expected_captures,'Unexpected capture files')
    results=[]; coordinates=[]
    for coordinate in plan['plans']:
        tasks=coordinate['tasks']; count=len(tasks)
        row=dict(coordinate=coordinate['coordinate'],planned=count,completed=0,pending=count,status='NO_DELTA' if not count else 'NOT_VISITED')
        capture_path=destination/(coordinate['child_sha256']+'.json')
        if not count or capture_path.name not in capture_names:
            coordinates.append(row)
            continue
        capture=snapshot.read(capture_path)
        digest=capture.pop('capture_sha256',None)
        _require(digest==runner._sha(capture),'Capture checksum differs')
        _require(set(capture)=={'schema','experiment_sha256','cli_sha256','tasks','prepared_inputs',
            'source_evidence','numerical_sources','runtime','panel_metadata'},'Capture schema fields differ')
        _require(capture.get('schema')=='ndx_joint_weight_batch_capture_v1'
            and capture.get('experiment_sha256')==plan['experiment_sha256'] and capture.get('cli_sha256')==cli_hash
            and runner._json_bytes(capture['tasks'])==runner._json_bytes(tasks)
            and capture['numerical_sources']==numerical and capture['runtime']==runtime,
            'Capture source/task/runtime binding differs')
        for task in tasks:
            runner._validate_task(task)
        inputs={k:_restore_input(v) for k,v in capture['prepared_inputs'].items()}
        evidence=_restore(capture['source_evidence'])
        _require(runner._json_bytes(runner._normalize(evidence))==runner._json_bytes(capture['source_evidence']),
                 'Capture evidence does not roundtrip')
        _require(evidence['experiment_sha256']==plan['experiment_sha256'] and evidence['cli_sha256']==cli_hash,
                 'Capture evidence binding differs')
        context=dict(schema='ndx_joint_weight_checkpoint_v1',tasks=tasks,
            prepared_inputs={k:runner._panel_context(v) for k,v in inputs.items()},
            source_evidence=runner._normalize(evidence),numerical_sources=capture['numerical_sources'],runtime=capture['runtime'])
        context_hash=runner._sha(context)
        directory=runner.CHECKPOINT_ROOT/context_hash
        names=snapshot.directory(directory)
        expected={'context.json'}|{task['job_id']+'.json' for task in tasks}
        _require(names<=expected,'Unexpected checkpoint files')
        if 'context.json' not in names:
            _require(not names,'Checkpoints without context')
            row['status']='CAPTURED_PENDING';coordinates.append(row);continue
        stored=snapshot.read(directory/'context.json')
        _require(runner._json_bytes(stored)==runner._json_bytes(context),'Captured runner context differs')
        row['context_sha256']=context_hash
        for task in tasks:
            filename=task['job_id']+'.json'
            if filename not in names:
                continue
            checkpoint=snapshot.read(directory/filename)
            digest=checkpoint.pop('checkpoint_sha256',None)
            _require(digest==runner._sha(checkpoint) and checkpoint.get('context_sha256')==context_hash
                and runner._json_bytes(checkpoint.get('task'))==runner._json_bytes(task)
                and checkpoint.get('status')=='EVALUATED'
                and set(checkpoint)=={'context_sha256','task','status','result'},'Checkpoint binding differs')
            result=_restore(checkpoint['result'])
            _require(runner._json_bytes(runner._normalize(result))==runner._json_bytes(checkpoint['result']),
                     'Result encoding differs')
            _require(result.get('tickers')==task['tickers'] and result.get('weight_spec')==task['weight_spec']
                     and type(result.get('holding_count')) is int and result['holding_count']==task['holding_count'],
                     'Result portfolio identity differs')
            for field in RETURN_FIELDS+DRAWDOWN_FIELDS:
                _require(type(result[field]) in (int,float) and math.isfinite(result[field]),'Invalid metric')
            for field in ('declared_constraints_passed','whole_lot_executable_all_windows'):
                _require(type(result[field]) is bool,'Invalid result boolean')
            _require(isinstance(result.get('constraint_failure_reasons'),str),'Invalid constraint failure reasons')
            joint=all(result[f]>=0 for f in RETURN_FIELDS) and all(result[f]<=0 for f in DRAWDOWN_FIELDS)
            results.append(dict(job_id=task['job_id'],coordinate=coordinate['coordinate'],tickers=task['tickers'],
                weight_spec=task['weight_spec'],fractional_joint_noninferior=joint,
                declared_constraints_passed=result['declared_constraints_passed'],
                fractional_metrics={f:result[f] for f in RETURN_FIELDS+DRAWDOWN_FIELDS},
                constraint_failure_reasons=result['constraint_failure_reasons'],
                whole_lot={k:v for k,v in result.items() if k.startswith('whole_lot_')},
                component_noninferior={f:result[f]>=0 for f in RETURN_FIELDS}|{f:result[f]<=0 for f in DRAWDOWN_FIELDS},
                user_preference_reference=task['tickers']==PREFERENCE))
            row['completed']+=1
        row['pending']=count-row['completed']
        row['status']='COMPLETE' if not row['pending'] else 'PARTIAL'
        coordinates.append(row)
    snapshot.verify()
    _require(runner._source_hashes()==numerical,'Numerical source changed during observation')
    completed=len(results)
    _require(sum(row['planned'] for row in coordinates)==plan['planned'],'Global denominator differs')
    return dict(status='COMPLETE_CAPTURED_RESULTS' if completed==plan['planned'] else 'PARTIAL_CAPTURED_RESULTS',
        planned=plan['planned'],completed=completed,pending=plan['planned']-completed,coordinates=coordinates,
        component_noninferior_counts={f:sum(r['component_noninferior'][f] for r in results) for f in RETURN_FIELDS+DRAWDOWN_FIELDS},
        fractional_joint_noninferior=sum(r['fractional_joint_noninferior'] for r in results),
        declared_constraints_passed=sum(r['declared_constraints_passed'] for r in results),
        declared_and_eight_component_noninferior=sum(r['fractional_joint_noninferior'] and r['declared_constraints_passed'] for r in results),
        whole_lot_executable=sum(r['whole_lot']['whole_lot_executable_all_windows'] for r in results),
        user_preference_results=[r for r in results if r['user_preference_reference']],
        user_preference_tasks=[dict(job_id=t['job_id'],coordinate=p['coordinate'],weight_spec=t['weight_spec'],
            status='EVALUATED' if any(r['job_id']==t['job_id'] for r in results) else 'PENDING')
            for p in plan['plans'] for t in p['tasks'] if t['tickers']==PREFERENCE],
        user_preference_scope='DELTA_TASKS_ONLY_NOT_ALL_HISTORICAL_REFERENCE_ROWS',
        evaluated_results=results,missing_results_are_economic_failures=False,
        economic_recomputation_performed=False,external_source_authenticity_verified=False,promotion_allowed=False)


def run(experiment_path):
    watched=[Path(__file__),Path(batch.__file__),ROOT/'scripts/ndx_joint_weight_verify.py']+[ROOT/p for p in batch.PROTECTED]
    before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}
    try:
        plan=batch.build_plan(experiment_path)
        result=inspect_plan(plan,cli_hash=before[Path(batch.__file__)])
        plan['sources'].validate_unchanged()
        return result
    finally:
        _require(before=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in watched},'Source/live files changed during observation')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment',required=True)
    args=parser.parse_args()
    print(json.dumps(run(args.experiment),ensure_ascii=False,indent=2))
