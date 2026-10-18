"""Create-only admitted cash descriptor from an independently reviewed capture.

No search or service activation. Review contract: status PASS and source_hashes
must bind all four preparation artifacts plus this preparer and compiler bytes.
"""
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath

from data.current_quantity_portfolio_research_v2 import (
    CurrentQuantityPortfolioResearchV2, WORKER, WORKER_SHA256, WORKER_DEPENDENCIES)
from data.current_research_capital_decision_v2 import VERSION
from data.current_quantity_v2_monthly_training import compile_saved_training


def prepare(*, root, preparation_path, preparation_sha256, review_path,
            review_sha256, output_directory):
    root = Path(root).resolve()
    def path(name):
        if (not isinstance(name, str) or not name or '\\' in name or ':' in name
                or PurePosixPath(name).is_absolute()
                or any(x in ('', '.', '..') for x in name.split('/'))):
            raise ValueError('UNSAFE_PATH')
        result = (root / name).resolve()
        if not result.is_relative_to(root): raise ValueError('PATH_ESCAPE')
        return result
    files, pins = {}, {}
    def pin(name, expected=None):
        p = path(name)
        if p.stat().st_size > 32 * 1024 * 1024: raise ValueError('SOURCE_TOO_LARGE')
        raw = p.read_bytes(); digest = sha256(raw).hexdigest()
        if expected is not None and digest != expected: raise ValueError('HASH_MISMATCH:' + name)
        if name in pins and pins[name] != digest: raise ValueError('PIN_CONFLICT:' + name)
        files[name] = raw; pins[name] = digest
        if len(pins) > 2000 or sum(map(len, files.values())) > 128 * 1024 * 1024:
            raise ValueError('SOURCE_BUDGET')
        return json.loads(raw) if name.endswith('.json') else raw
    prep = pin(preparation_path, preparation_sha256)
    review = pin(review_path, review_sha256)
    folder = str(PurePosixPath(preparation_path).parent)
    names = [preparation_path] + [folder + '/' + n + '.json' for n in ('manifest', 'input', 'report')]
    required_review = names + ['scripts/prepare_monthly_captured_training.py',
                              'data/current_quantity_v2_monthly_training.py']
    if review.get('status') != 'PASS': raise ValueError('INDEPENDENT_REVIEW_REQUIRED')
    for name in required_review:
        expected = review.get('source_hashes', {}).get(name)
        if not expected: raise ValueError('REVIEW_ARTIFACT_BINDING_REQUIRED:' + name)
        pin(name, expected)
    if prep['status'] != 'READY_CONDITIONAL': raise ValueError('PREPARATION_NOT_READY')
    for name, digest in prep['source_hashes'].items(): pin(name, digest)
    rebuilt = compile_saved_training(dict(files=files, source_hashes=pins, documents={}), folder + '/manifest.json')
    saved_input = json.loads(files[folder + '/input.json'])
    if rebuilt['input'] != prep['input'] or saved_input != prep['input']:
        raise ValueError('COMPILED_INPUT_MISMATCH')
    for name in sorted(set(WORKER_DEPENDENCIES) | {WORKER,
            'data/current_quantity_portfolio_research_v2.py',
            'data/current_quantity_v2_service_factory.py',
            'scripts/prepare_captured_cash_research_descriptor.py'}):
        pin(name, WORKER_SHA256 if name == WORKER else None)
    output = path(output_directory)
    if output.exists(): raise ValueError('CREATE_ONLY_OUTPUT_EXISTS')
    admission_path = output_directory + '/admission.json'
    admission = dict(status='ADMITTED_CASH_RESEARCH_V2', method=VERSION,
        input_path=folder + '/input.json', input_sha256=pins[folder + '/input.json'],
        decision_date=saved_input['search_arguments']['decision_date'],
        scope='SERVER_OWNED_SAVED_CONDITIONAL_CASH_RESEARCH_INPUT_ONLY',
        research_only=True, execution_blocked=True, automatic_search_authorized=False,
        transaction_or_production_admission=False,
        independent_review=dict(path=review_path, sha256=review_sha256))
    raw = (json.dumps(admission, ensure_ascii=False, sort_keys=True, indent=2)+'\n').encode()
    pins[admission_path] = sha256(raw).hexdigest()
    descriptor = dict(input_path=folder + '/input.json', admission_path=admission_path,
                      source_hashes=dict(sorted(pins.items())))
    output.mkdir(parents=True, exist_ok=False)
    with path(admission_path).open('xb') as stream: stream.write(raw)
    # Validate every actual source and chart coordinate before publishing descriptor.
    CurrentQuantityPortfolioResearchV2(root=root, source_loader=lambda: descriptor)._load()
    descriptor_raw = (json.dumps(descriptor, ensure_ascii=False, sort_keys=True, indent=2)+'\n').encode()
    with (output/'descriptor.json').open('xb') as stream: stream.write(descriptor_raw)
    return dict(descriptor_path=output_directory+'/descriptor.json',
                descriptor_sha256=sha256(descriptor_raw).hexdigest(),
                source_pins=len(pins), search_calls=0, book_calls=0)
