"""Read-only full-coordinate v3 index; no portfolio selection or training."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_joint_weight_batch_v3 as batch
from scripts import ndx_joint_weight_progress_v3 as progress

EXPERIMENT = ROOT/'data/cache/research/ndx_joint_weight_experiment_v1/experiment.json'
FROZEN_INPUTS = ROOT/'data/cache/research/ndx_joint_weight_experiment_v2/frozen_inputs.json'
_SOURCES = [Path(__file__).resolve(), Path(progress.__file__), Path(progress.original.__file__)]
_LOADED = {str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in _SOURCES}


def _key(coordinate):
    return batch.old_runner._json_bytes(coordinate)


def _index(versioned, report):
    """Join only exact coordinates; never collapse source segments or no-delta."""
    planned = versioned['plan']
    if report['namespace_sha256'] != versioned['namespace_sha256']:
        raise ValueError('Progress namespace differs from plan')
    coordinate_map = {_key(row['coordinate']):row for row in report['coordinates']}
    if len(coordinate_map) != len(report['coordinates']) or len(coordinate_map) != len(planned['plans']):
        raise ValueError('Coordinate denominator mismatch/duplicate')
    results = {}
    for row in report['evaluated_results']:
        key = (_key(row['coordinate']), row['job_id'])
        if key in results:
            raise ValueError('Duplicate evaluated task')
        results[key] = row
    rows = []
    for coordinate_plan in planned['plans']:
        coordinate = coordinate_plan['coordinate']
        key = _key(coordinate)
        if key not in coordinate_map:
            raise ValueError('Planned coordinate absent from progress')
        observed = coordinate_map.pop(key)
        tasks = coordinate_plan['tasks']
        if len({task['job_id'] for task in tasks}) != len(tasks) or observed['planned'] != len(tasks):
            raise ValueError('Coordinate task denominator mismatch')
        indexed = []
        for task in tasks:
            batch.old_runner._validate_task(task)
            if any(task[field] != value for field,value in coordinate.items()):
                raise ValueError('Task coordinate identity differs')
            result = results.pop((key, task['job_id']), None)
            if result is not None and (result['tickers'] != task['tickers'] or result['weight_spec'] != task['weight_spec']):
                raise ValueError('Progress task identity differs')
            indexed.append(dict(task=deepcopy(task), status='EVALUATED' if result is not None else 'MISSING_CHECKPOINT'))
        completed = sum(row['status']=='EVALUATED' for row in indexed)
        if completed != observed['completed'] or len(tasks)-completed != observed['pending']:
            raise ValueError('Coordinate completion denominator differs')
        if not tasks and observed['status'] != 'NO_DELTA':
            raise ValueError('Empty delta must remain NO_DELTA')
        if completed and not observed.get('context_sha256'):
            raise ValueError('Evaluated tasks require captured context identity')
        rows.append(dict(**deepcopy(coordinate), child_path=coordinate_plan['child_path'],
            context_sha256=observed.get('context_sha256'), status=observed['status'],
            planned=len(tasks), completed=completed, pending=len(tasks)-completed, tasks=indexed))
    if coordinate_map or results or sum(row['planned'] for row in rows) != planned['planned']:
        raise ValueError('Unmatched global coordinate/task denominator')
    total = sum(row['completed'] for row in rows)
    if total != report['completed'] or planned['planned']-total != report['pending']:
        raise ValueError('Global completion denominator differs')
    return dict(schema='ndx_dynamic_training_plan_v1', coordinates=rows,
        namespace_sha256=versioned['namespace_sha256'], capture_root=str(versioned['capture_destination']),
        summary=dict(coordinate_count=len(rows), planned=planned['planned'], completed=total,
            pending=planned['planned']-total, status_counts=dict(Counter(row['status'] for row in rows)),
            source_batches=sorted({row['source_batch'] for row in rows}),
            source_segment_coordinate_counts=dict(Counter(row['source_batch'] for row in rows))),
        no_delta_means='NO_ADDITIONAL_V3_TASKS_NOT_MISSING_DATE_NOT_ECONOMIC_FAILURE',
        scope='FULL_CAPTURED_V3_DELTA_PLAN_NOT_ALL_BASE_CANDIDATES_OR_FINAL_K_POOL',
        missing_results_are_economic_failures=False, economic_recomputation_performed=False,
        portfolio_selected=False, promotion_allowed=False)


def load_training_plan(experiment_path=EXPERIMENT, frozen_input_manifest_path=FROZEN_INPUTS):
    """Validate real plan/captures/context/checkpoint bindings then discard metrics."""
    if any(hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest for path,digest in _LOADED.items()):
        raise ValueError('Training index source drift')
    versioned = batch.build_versioned_plan(experiment_path, frozen_input_manifest_path)
    report = progress.inspect_versioned_plan(versioned)
    result = _index(versioned, report)
    sources = dict(_LOADED)
    sources.update({str(ROOT/path):digest for path,digest in versioned['dependencies'].items()})
    for observer in (versioned['plan']['sources'], versioned['frozen_bundle']['sources']):
        observer.validate_unchanged()
        sources.update({str(path):digest for path,digest in observer.observed.items()})
    if any(hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest for path,digest in sources.items()):
        raise ValueError('Training index sources changed during observation')
    result.update(source_hashes=sources, experiment_sha256=versioned['plan']['experiment_sha256'],
        frozen_input_manifest_sha256=versioned['frozen_bundle']['manifest_sha256'],
        capture_context_checkpoint_bindings_verified=True, external_source_authenticity_verified=False)
    return result


if __name__=='__main__':
    result=load_training_plan()
    print(json.dumps({key:value for key,value in result.items() if key not in ('coordinates','source_hashes')},indent=2))
