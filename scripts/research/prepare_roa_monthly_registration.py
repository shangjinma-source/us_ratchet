"""Prepare a month registry release; never activate, restart, or write accounts."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
from data.roa_monthly_loader import RoaMonthlySelectionLoader


def prepare(*, root, active_path, active_sha256, receipt_path, receipt_sha256, output_directory):
    root = Path(root).resolve()
    checked = {}
    def path(name):
        candidate = Path(name)
        if candidate.is_absolute() or '..' in candidate.parts or ':' in name:
            raise ValueError('PATH_OUTSIDE_ROOT')
        result = (root / candidate).resolve()
        if not result.is_relative_to(root): raise ValueError('PATH_OUTSIDE_ROOT')
        return result
    def read(name, expected):
        raw = path(name).read_bytes()
        if sha256(raw).hexdigest() != expected: raise ValueError('SOURCE_HASH_CHANGED:' + name)
        checked[name] = expected
        return json.loads(raw)
    active_raw = path(active_path).read_bytes()
    if sha256(active_raw).hexdigest() != active_sha256: raise ValueError('SOURCE_HASH_CHANGED:' + active_path)
    active = read(active_path, active_sha256)
    if active.get('schema') != 'STRATEGY_SERVER_ACTIVE_V6': raise ValueError('ACTIVE_SCHEMA_INVALID')
    configuration = read(active['configuration_path'], active['configuration_sha256'])
    if configuration.get('schema') != 'ROA_UNIFIED_PREPARATION_V34': raise ValueError('V34_REQUIRED')
    for name, expected in configuration['source_pins'].items():
        if sha256(path(name).read_bytes()).hexdigest() != expected: raise ValueError('CODE_SOURCE_CHANGED:' + name)
        checked[name] = expected
    base = configuration['base_v33']
    read(base['path'], base['sha256'])
    receipt = read(receipt_path, receipt_sha256)
    if receipt.get('status') != 'PREPARED_VERIFIED_NOT_REGISTERED': raise ValueError('MONTH_PACKAGE_NOT_PREPARED')
    month = receipt['month']
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month): raise ValueError('MONTH_INVALID')
    existing = configuration['roa'].get('monthly_selections', {})
    if month in existing: raise ValueError('MONTH_ALREADY_REGISTERED')
    proposal_raw = path(receipt['registry_proposal']).read_bytes()
    proposal = json.loads(proposal_raw)
    checked[receipt['registry_proposal']] = sha256(proposal_raw).hexdigest()
    expected_spec = dict(path=receipt['runtime_path'], sha256=receipt['runtime_sha256'])
    if proposal != {month: expected_spec}: raise ValueError('REGISTRY_RECEIPT_CONFLICT')
    artifact = read(expected_spec['path'], expected_spec['sha256'])
    for name in artifact['source_hashes']: path(name)
    session = artifact['first_execution_session']
    if session[:7] != month or artifact['decision_date'] != receipt['decision_date'] or artifact['decision_date'] >= session:
        raise ValueError('MONTH_SELECTION_SCOPE_INVALID')
    loaded = RoaMonthlySelectionLoader(root=root, registry=proposal)(session)
    checked.update(loaded['source_hashes'])
    originals = [name for name in loaded['source_hashes'] if name.replace('\\', '/').endswith('/selection.source.json')]
    if len(originals) != 1: raise ValueError('ORIGINAL_SELECTION_REQUIRED')
    original = read(originals[0], loaded['source_hashes'][originals[0]])
    if original['selection_id'] != receipt['selection_id'] or any(original[key] != loaded[key] for key in ('selection','weights','securities','decision_date','effective_month')):
        raise ValueError('RECEIPT_SELECTION_CONFLICT')
    # Existing approved months are validated too; no silent replacement of their pins.
    for old_month, spec in existing.items():
        old = read(spec['path'], spec['sha256'])
        for name in old['source_hashes']: path(name)
        old_loaded = RoaMonthlySelectionLoader(root=root, registry={old_month: spec})(old['first_execution_session'])
        checked.update(old_loaded['source_hashes'])
    updated = deepcopy(configuration)
    updated['roa']['monthly_selections'] = {**existing, **proposal}
    output = path(output_directory)
    if output.exists(): raise ValueError('OUTPUT_ALREADY_EXISTS')
    # Recheck the active/source snapshot immediately before producing the proposal.
    for name, expected in checked.items():
        if sha256(path(name).read_bytes()).hexdigest() != expected: raise ValueError('SOURCE_CHANGED_DURING_PREPARATION')
    output.mkdir(parents=True)
    def save(name, value):
        raw = json.dumps(value, indent=2).encode()
        target = output / name
        with target.open('xb') as stream: stream.write(raw)
        return dict(path=target.relative_to(root).as_posix(), sha256=sha256(raw).hexdigest())
    reference = save('deploy-v34.json', updated)
    next_active = deepcopy(active)
    next_active.update(configuration_path=reference['path'], configuration_sha256=reference['sha256'])
    save('next_active.json', next_active)
    # Exact previous active bytes, suitable for restoring the prior pointer.
    with (output / 'rollback_active.json').open('xb') as stream: stream.write(active_raw)
    if sha256(path(active_path).read_bytes()).hexdigest() != active_sha256:
        raise ValueError('ACTIVE_CHANGED_DURING_PREPARATION')
    return save('preparation.json', dict(status='PREPARED_NOT_ACTIVATED', month=month,
        expected_active=dict(path=active_path, sha256=active_sha256), receipt=dict(path=receipt_path, sha256=receipt_sha256),
        configuration=reference, account_writes=False, restart=False,
        requirement='Deployment must recheck expected active hash and prepared sources before switching.'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('active-path','active-sha256','receipt-path','receipt-sha256','output-directory'):
        parser.add_argument('--'+name, required=True)
    args = vars(parser.parse_args())
    print(json.dumps(prepare(root=Path(__file__).resolve().parents[2], **args)))
