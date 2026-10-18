"""Execution-source envelope for the one-retarget paper ledger.

Freeze raw/receipt/unit bytes, not broker truth or training-source admission.
Replay requires no source files and preserves the original observation time.
"""
import base64
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from data.current_research_intraday_buy_plan import _require
from data.current_research_intraday_execution_reference import read_intraday_execution_reference
from data.current_research_intraday_retarget_ledger import accept_retarget_proposal, review_retarget_ledger

SCHEMA = 'INTRADAY_RETARGET_EXECUTION_SOURCE_ENVELOPE_V1'
MAX_TOTAL_BYTES = 128 * 1024 * 1024
JOURNAL_SOURCE = 'INTRADAY_JOURNAL_OBSERVATION_V1'


def read_execution_evidence_reference(*, root, arguments, now, frozen_files=None):
    """Dispatch original source formats; journal events are not linear receipts."""
    if 'source_kind' not in arguments:
        return read_intraday_execution_reference(root=root, frozen_files=frozen_files, now=now, **arguments)
    _require(arguments['source_kind'] == JOURNAL_SOURCE and set(arguments) == {
        'source_kind', 'binding', 'current_reference', 'event_hashes', 'source_hashes', 'security_id'},
        'JOURNAL_EXECUTION_INPUT_SCHEMA')
    _require(arguments['security_id'] == arguments['binding']['security_id'], 'JOURNAL_SECURITY_MISMATCH')
    from data.current_research_intraday_journal_reference import read_journal_execution_reference
    reference = read_journal_execution_reference(root=root, binding=arguments['binding'],
        current_reference=arguments['current_reference'], event_hashes=arguments['event_hashes'],
        now=now, frozen_files=frozen_files)
    _require(reference['source_hashes'] == arguments['source_hashes'], 'JOURNAL_SOURCE_PIN_DOMAIN_MISMATCH')
    return reference


def _needed(inputs, units, pins):
    required = {}
    _require(isinstance(inputs, dict) and inputs and set(inputs) == set(units), 'EXECUTION_EVIDENCE_DOMAIN_MISMATCH')
    for sid, arguments in inputs.items():
        _require(not {'root', 'now', 'frozen_files'} & set(arguments) and arguments['security_id'] == sid, 'SOURCE_INPUT_SCHEMA')
        for name, digest in arguments['source_hashes'].items():
            _require(pins.get(name) == digest, 'EXECUTION_PIN_MISMATCH')
            required[name] = digest
        for name in units[sid]['source_references']:
            required[name] = pins[name]
    return required


def _path(name):
    _require(isinstance(name, str) and name and '\\' not in name, 'INVALID_SOURCE_PATH')
    value = Path(name)
    _require(not value.is_absolute() and not value.drive and '..' not in value.parts, 'SOURCE_OUTSIDE_ROOT')
    return value


def replay_execution_evidence(evidence):
    """Verify every frozen byte and replay references at their original checked_at."""
    _require(set(evidence) == {'execution_inputs', 'units', 'source_hashes', 'files', 'references'}, 'EXECUTION_EVIDENCE_SCHEMA')
    required = _needed(evidence['execution_inputs'], evidence['units'], evidence['source_hashes'])
    _require(set(evidence['files']) == set(required) == set(evidence['source_hashes']), 'FROZEN_SOURCE_DOMAIN_MISMATCH')
    files, total = {}, 0
    for name, encoded in evidence['files'].items():
        _path(name)
        _require(isinstance(encoded, str) and len(encoded) <= 45 * 1024 * 1024, 'FROZEN_SOURCE_TOO_LARGE')
        raw = base64.b64decode(encoded, validate=True)
        total += len(raw)
        _require(len(raw) <= 32 * 1024 * 1024 and total <= MAX_TOTAL_BYTES, 'FROZEN_SOURCE_TOO_LARGE')
        _require(sha256(raw).hexdigest() == required[name], 'FROZEN_SOURCE_HASH_MISMATCH')
        files[name] = raw
    references = {}
    _require(set(evidence['references']) == set(evidence['execution_inputs']), 'REFERENCE_DOMAIN_MISMATCH')
    for sid, arguments in evidence['execution_inputs'].items():
        original = evidence['references'][sid]
        replay_at = original['replay_at'] if arguments.get('source_kind') == JOURNAL_SOURCE else original['checked_at']
        references[sid] = read_execution_evidence_reference(root='.', frozen_files=files,
            now=replay_at, arguments=arguments)
    _require(references == evidence['references'], 'FROZEN_REFERENCE_REPLAY_MISMATCH')
    return references


def freeze_execution_evidence(*, root, sizing_inputs, execution_inputs):
    base = Path(root).resolve()
    units = sizing_inputs['execution_unit_continuity']
    required = _needed(execution_inputs, units, sizing_inputs['source_hashes'])
    files, total = {}, 0
    for name, digest in required.items():
        full = (base / _path(name)).resolve()
        _require(full.is_relative_to(base) and full.stat().st_size <= 32 * 1024 * 1024, 'SOURCE_OUTSIDE_ROOT_OR_TOO_LARGE')
        raw = full.read_bytes()
        total += len(raw)
        _require(total <= MAX_TOTAL_BYTES and sha256(raw).hexdigest() == digest, 'SOURCE_SIZE_OR_HASH_MISMATCH')
        files[name] = base64.b64encode(raw).decode('ascii')
    evidence = dict(execution_inputs=deepcopy(execution_inputs), units=deepcopy(units),
        source_hashes=required, files=files, references=deepcopy(sizing_inputs['execution_references']))
    replay_execution_evidence(evidence)
    return evidence


def accept_retarget_with_execution_evidence(state, proposal, *, root, sizing_inputs,
        execution_inputs, market_session, operation_id, now):
    evidence = freeze_execution_evidence(root=root, sizing_inputs=sizing_inputs, execution_inputs=execution_inputs)
    ledger = accept_retarget_proposal(state, proposal, sizing_inputs=sizing_inputs,
        market_session=market_session, operation_id=operation_id, now=now)
    return dict(schema=SCHEMA, ledger=ledger, retarget_acceptance_id=ledger['retarget_acceptance_id'],
        execution_evidence=evidence, execution_source_bytes_verified=True,
        selection_source_bytes_reverified=False, source_authenticated=False, real_account=False)


def review_source_verified_retarget(envelope):
    _require(envelope.get('schema') == SCHEMA, 'SOURCE_ENVELOPE_SCHEMA')
    ledger = review_retarget_ledger(envelope['ledger'])
    _require(envelope['retarget_acceptance_id'] == ledger['retarget_acceptance_id'], 'ENVELOPE_ACCEPTANCE_MISMATCH')
    evidence = envelope['execution_evidence']
    references = replay_execution_evidence(evidence)
    inputs = ledger['retarget_acceptance']['sizing_inputs']
    _require(references == inputs['execution_references'] and evidence['units'] == inputs['execution_unit_continuity'], 'ENVELOPE_LEDGER_EVIDENCE_MISMATCH')
    _require(all(inputs['source_hashes'].get(name) == digest for name, digest in evidence['source_hashes'].items()), 'ENVELOPE_LEDGER_PIN_MISMATCH')
    expected = dict(schema=SCHEMA, ledger=ledger, retarget_acceptance_id=ledger['retarget_acceptance_id'],
        execution_evidence=evidence, execution_source_bytes_verified=True,
        selection_source_bytes_reverified=False, source_authenticated=False, real_account=False)
    _require(expected == envelope, 'SOURCE_ENVELOPE_FIELDS_MISMATCH')
    return deepcopy(envelope)
