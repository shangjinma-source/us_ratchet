"""One registered four-book batch and review, sharing one wall-clock budget."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import time

from backtest.bounded_research_process import run_worker


def run_batch(*, registration, output_directory):
    registered = deepcopy(registration)
    jobs = registered['books']
    if [job['id'] for job in jobs] != ['L-A', 'L-B', 'E-A', 'E-B']:
        raise ValueError('FIXED_FOUR_BOOK_ORDER_REQUIRED')
    total = registered['total_seconds']
    new_book_limit = registered['new_book_cutoff_seconds']
    if not 0 < new_book_limit <= 5*3600 or not new_book_limit < total <= 6*3600:
        raise ValueError('FIXED_TOTAL_BUDGET_REQUIRED')
    pins = registered['source_sha256']
    if not pins:
        raise ValueError('FROZEN_SOURCE_PINS_REQUIRED')
    for name, expected in pins.items():
        if sha256(Path(name).read_bytes()).hexdigest() != expected:
            raise ValueError('SOURCE_CHANGED: '+name)
    for job in [*jobs, registered['review']]:
        if pins.get(job['script']) != job['script_sha256']:
            raise ValueError('WORKER_NOT_IN_FROZEN_SOURCE_PINS')
    output = Path(output_directory).resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output/'registration.json').write_text(json.dumps(registered, indent=2)+'\n', encoding='utf-8')
    started = time.monotonic()
    result = dict(status='RUNNING', completed_books=[], workers=[], retry_allowed=False,
                  total_seconds=total, new_book_cutoff_seconds=new_book_limit)

    def save():
        result['elapsed_seconds'] = time.monotonic()-started
        temporary = output/'batch.pending.json'
        temporary.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        temporary.replace(output/'batch.json')

    save()
    try:
        for index, job in enumerate([*jobs, registered['review']]):
            reviewing = index == len(jobs)
            elapsed = time.monotonic()-started
            if elapsed >= total or (not reviewing and elapsed >= new_book_limit):
                result['status'] = 'BUDGET_STOP_INCONCLUSIVE'
                break
            # Check all pins again: a prior worker must not rewrite inputs/code.
            for name, expected in pins.items():
                if sha256(Path(name).read_bytes()).hexdigest() != expected:
                    raise ValueError('SOURCE_CHANGED_DURING_BATCH: '+name)
            remaining = total-(time.monotonic()-started)
            if remaining <= 0:
                result['status'] = 'BUDGET_STOP_INCONCLUSIVE'
                break
            name = 'review' if reviewing else job['id']
            artifact = output/(name+'-result.json')
            if artifact.exists():
                raise ValueError('UNEXPECTED_PREEXISTING_RESULT')
            worker = run_worker(script=job['script'], expected_sha256=job['script_sha256'],
                                arguments=[*job['arguments'], '--result', str(artifact)],
                                output_directory=output/name, timeout_seconds=remaining)
            result['workers'].append(dict(id=name, result=worker))
            if worker['status'] != 'WORKER_EXITED_REVIEW_REQUIRED':
                result['status'] = 'WORKER_STOP_INCONCLUSIVE'
                break
            raw = artifact.read_bytes()
            document = json.loads(raw)
            if document.get('status') != ('REVIEW_COMPLETE' if reviewing else 'COMPLETE'):
                raise ValueError('INCOMPLETE_RESULT: '+name)
            if not reviewing:
                if document.get('book_id') != name:
                    raise ValueError('BOOK_ID_MISMATCH')
                result['completed_books'].append(dict(id=name, result_sha256=sha256(raw).hexdigest()))
            else:
                expected = {row['id']: row['result_sha256'] for row in result['completed_books']}
                if document.get('reviewed_book_sha256') != expected:
                    raise ValueError('REVIEW_DOES_NOT_BIND_ALL_FOUR_BOOKS')
                result.update(status='ARTIFACTS_READY_FOR_ASSESSMENT', review_sha256=sha256(raw).hexdigest())
            save()
    except Exception as error:
        result.update(status='FAILED_INCONCLUSIVE', error_type=type(error).__name__, detail=str(error))
        save()
        raise
    save()
    return result
