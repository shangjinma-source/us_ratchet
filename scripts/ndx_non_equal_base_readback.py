"""Read-only source-bound snapshot of an explicit non-equal base context."""
import hashlib
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_non_equal_base_runner as runner

_SELF = Path(__file__).resolve()
_LOADED = hashlib.sha256(_SELF.read_bytes()).hexdigest()


def _digest(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('Explicit SHA256 required')


def read_context(*, context_path, expected_context_sha256):
    """Missing jobs remain missing; concurrent new publications wait for next read."""
    _digest(expected_context_sha256)
    path = Path(context_path).resolve()
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_context_sha256:
        raise ValueError('Context SHA mismatch')
    context = runner._read(path)
    if runner._bytes(context) != raw:
        raise ValueError('Context changed during read')
    fields = {'schema','source_batch','universe_track','selection_date','tasks','training_semantics',
              'source_hashes','numerical_sources','planned','runtime'}
    if set(context) != fields or context['schema'] != 'ndx_non_equal_base_context_v1':
        raise ValueError('Exact independent base context required')
    tasks = context['tasks']
    if (type(tasks) is not list or type(context['planned']) is not int
            or context['planned'] != len(tasks) or not tasks):
        raise ValueError('Context task denominator differs')
    semantics = context['training_semantics']
    if runner.preparation._sha(semantics['payload']) != semantics['training_semantics_sha256']:
        raise ValueError('Training semantics SHA differs')
    for key in ('source_batch','universe_track'):
        if semantics['payload'][key] != context[key]:
            raise ValueError('Semantics coordinate differs')
    identifiers = set()
    for task in tasks:
        if (task['schema_version'] != runner.preparation.SCHEMA
                or runner.preparation._sha({k:v for k,v in task.items() if k != 'job_id'}) != task['job_id']
                or task['job_id'] in identifiers):
            raise ValueError('Task identity differs')
        _digest(task['job_id']); identifiers.add(task['job_id'])
        if any(task[key] != context[key] for key in ('source_batch','universe_track','selection_date')):
            raise ValueError('Task coordinate differs')
        if (task['decision_data_end'] != semantics['payload']['decision_data_end']
                or task['training_semantics_sha256'] != semantics['training_semantics_sha256']):
            raise ValueError('Task training semantics differs')
    sources = dict(context['source_hashes'])
    for mapping in (runner._LOADED, runner.evaluator._sources(), context['numerical_sources']):
        for source, digest in mapping.items():
            if sources.get(source) != digest:
                raise ValueError('Required source binding differs')
    if context['numerical_sources'] != runner.evaluator._sources():
        raise ValueError('Numerical closure differs')
    for source, digest in sources.items():
        _digest(digest)
        if not Path(source).is_absolute():
            raise ValueError('Absolute source required')
    sources[str(_SELF)] = _LOADED
    sources[str(path)] = expected_context_sha256
    runner._verify_sources(sources)
    records = []; missing = []
    # Freeze existence before traversal. A concurrently published missing job
    # remains explicitly missing in this snapshot, never silently completed.
    available = {task['job_id'] for task in tasks if (path.parent/(task['job_id']+'.json')).is_file()}
    for task in tasks:
        if task['job_id'] not in available:
            missing.append(task['job_id']); continue
        checkpoint = path.parent/(task['job_id']+'.json')
        before = checkpoint.read_bytes()
        result = runner._read_checkpoint(checkpoint, expected_context_sha256, task, context['numerical_sources'])
        if checkpoint.read_bytes() != before:
            raise ValueError('Checkpoint changed during read')
        digest = hashlib.sha256(before).hexdigest()
        sources[str(checkpoint)] = digest
        records.append(dict(task=task, result=result, checkpoint_path=str(checkpoint), checkpoint_sha256=digest))
    runner._verify_sources(sources)
    return dict(schema='ndx_non_equal_base_readback_v1', context_path=str(path),
        context_sha256=expected_context_sha256, context=context, records=records,
        planned=len(tasks), completed=len(records), missing=len(missing), missing_job_ids=missing,
        status='COMPLETE' if not missing else 'PARTIAL', source_hashes=sources,
        whole_lot_status='NOT_EVALUATED', full_portfolio_optimization_complete=False,
        promotion_allowed=False)
