"""Saved execution receipts and unit-source bytes to a pure retarget proposal.

Selection and its inputs are the trusted server's previously reviewed pure
selection result. This adapter adds execution evidence, not selection admission.
"""
from hashlib import sha256
from pathlib import Path

from data.current_research_intraday_buy_plan import _require
from data.current_research_intraday_buy_plan import _time
from data.current_research_intraday_retarget_evidence import read_execution_evidence_reference
from data.current_research_intraday_retarget_sizing import build_intraday_retarget_sizing


def review_saved_intraday_retarget(state, *, root, selection, selection_inputs,
        execution_inputs, execution_unit_continuity, source_hashes, now):
    """No capture or activation. Root, receipt tips and unit reviews are server-owned."""
    base = Path(root).resolve()
    _require(isinstance(execution_inputs, dict) and execution_inputs, 'EXECUTION_INPUTS_REQUIRED')
    references = {}
    for sid, inputs in execution_inputs.items():
        _require(isinstance(inputs, dict) and not {'root', 'now', 'frozen_files'} & set(inputs)
            and inputs.get('security_id') == sid, 'EXECUTION_INPUT_IDENTITY_MISMATCH')
        references[sid] = read_execution_evidence_reference(root=root, now=now, arguments=inputs)
    _require(isinstance(execution_unit_continuity, dict)
        and set(execution_unit_continuity) == set(references), 'EXECUTION_UNIT_DOMAIN_MISMATCH')
    for unit in execution_unit_continuity.values():
        paths = unit['source_references']
        _require(isinstance(paths, list) and paths, 'UNIT_SOURCE_REFERENCES_REQUIRED')
        for name in paths:
            _require(isinstance(name, str) and name and '\\' not in name, 'INVALID_UNIT_SOURCE_PATH')
            path = Path(name)
            _require(not path.is_absolute() and not path.drive and '..' not in path.parts, 'UNIT_SOURCE_OUTSIDE_ROOT')
            full = (base / path).resolve()
            _require(full.is_relative_to(base) and full.stat().st_size <= 32 * 1024 * 1024, 'UNIT_SOURCE_OUTSIDE_ROOT_OR_TOO_LARGE')
            _require(sha256(full.read_bytes()).hexdigest() == source_hashes[name], 'UNIT_SOURCE_HASH_MISMATCH')
    result = build_intraday_retarget_sizing(state, selection=selection, selection_inputs=selection_inputs,
        execution_references=references, execution_unit_continuity=execution_unit_continuity,
        source_hashes=source_hashes, now=now)
    if result['status'] == 'READY':
        result.update(execution_source_bytes_verified=True, latest_tip_authenticated=False,
            complete_corporate_actions_verified=False)
    return result


def review_saved_monthly_retarget(state, *, root, monthly_inputs, selection_at,
        execution_inputs, execution_unit_continuity, execution_source_hashes, now):
    """Compose both source readers; retain attestations outside the pure result.

    selection_at is the server's saved selection time, not a client backdate.
    Replaying that frozen observation does not renew any execution deadline.
    """
    from data.current_research_intraday_monthly_sources import review_saved_intraday_monthly_selection
    _require(_time(selection_at) <= _time(now), 'SELECTION_AFTER_NOW')
    _require(not {'root', 'now'} & set(monthly_inputs), 'MONTHLY_INPUT_SCHEMA')
    enriched = review_saved_intraday_monthly_selection(state, root=root, now=selection_at, **monthly_inputs)
    _require(enriched['status'] == 'READY', 'MONTHLY_SELECTION_UNAVAILABLE:' + str(enriched.get('reason')))
    # Only fields added by our just-executed source reader leave the pure object.
    # No caller-supplied selection is stripped or trusted here.
    selection = dict(enriched)
    attestation = {key: selection.pop(key) for key in ('source_bytes_verified', 'training_bundle_sha256',
        'complete_corporate_actions_verified', 'universe_completeness_authenticated')}
    binding = selection['binding']
    capital = binding['capital']
    money = capital['capital']
    capital_inputs = dict(expected_revision=money['account_revision'],
        initial_capital_identity=money['initial_capital_identity'], valuation_quotes=money['valuation_quotes'],
        unit_continuity=money['unit_continuity'], source_hashes=money['source_hashes'], market_session=money['market_session'])
    selection_inputs = dict(capital=capital, capital_inputs=capital_inputs,
        training_input=binding['training_input'], target_month=binding['target_month'],
        selection_calendar=binding['selection_calendar'], source_hashes=binding['source_hashes'])
    pins = dict(binding['source_hashes'])
    for name, digest in execution_source_hashes.items():
        _require(name not in pins or pins[name] == digest, 'SOURCE_PIN_CONFLICT')
        pins[name] = digest
    result = review_saved_intraday_retarget(state, root=root, selection=selection,
        selection_inputs=selection_inputs, execution_inputs=execution_inputs,
        execution_unit_continuity=execution_unit_continuity, source_hashes=pins, now=now)
    if result['status'] == 'READY':
        result['selection_source_attestation'] = attestation
    return result
