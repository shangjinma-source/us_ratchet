"""One preparation bundle, published only by a complete manifest. Not activation."""
from copy import deepcopy
from hashlib import sha256
import json
import os

from core.strategy_account_ledger import canonical, require
from core.strategy_account_store import StrategyAccountStore
from core.strategy_account_split_store_v1 import SplitStrategyAccountStore
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.strategy_account_split_migration_v1 import checked_path, prepare_split_account
from data.strategy_split_risk_preparation_v1 import prepare_split_risk
from data.strategy_split_native_projection_v1 import project_native_split


FILES = ('account.sqlite3', 'risk.sqlite3', 'inputs.json')


def prepare_split_bundle(*, source_account_path, destination_directory, expected_revision,
                         action, risk_before, target, expected_proposal_id,
                         observations, expected_sessions, clock):
    source = checked_path(source_account_path)
    directory = checked_path(destination_directory)
    require(not source.is_relative_to(directory), 'SPLIT_BUNDLE_SOURCE_SCOPE')
    require(directory.parent.is_dir(), 'SPLIT_BUNDLE_PARENT_REQUIRED')
    # Freeze caller values across disk writes and account checks.
    inputs = deepcopy(dict(action=action, risk_before=risk_before, target=target,
        expected_proposal_id=expected_proposal_id, observations=observations, expected_sessions=expected_sessions))
    directory.mkdir(exist_ok=False)
    try:
        prepare_split_account(source_path=source, destination_path=directory/'account.sqlite3',
                                          expected_revision=expected_revision)
        store = SplitStrategyAccountStore(directory/'account.sqlite3', clock=clock)
        after, _ = store.append(inputs['action'], expected_revision=expected_revision)
        result = prepare_split_risk(destination_path=directory/'risk.sqlite3', account_after=after,
            action_id=inputs['action']['action_id'], **{key:value for key,value in inputs.items() if key != 'action'})
        (directory/'inputs.json').write_bytes(canonical(inputs))
        require(StrategyAccountStore(source).read()['revision'] == expected_revision, 'SPLIT_BUNDLE_SOURCE_CHANGED')
        manifest = dict(schema='SPLIT_PREPARATION_BUNDLE_V1', status='PREPARED_NOT_ACTIVATED',
            source_account_revision=expected_revision, account_revision=after['revision'], account_id=after['account_id'],
            action_id=inputs['action']['action_id'], target_id=inputs['target']['target_id'],
            proposal_id=expected_proposal_id, transition_id=result['transition_id'],
            risk_state_sha256=sha256(canonical(result['final_state'])).hexdigest(),
            files={name:sha256((directory/name).read_bytes()).hexdigest() for name in FILES},
            source_authenticated=False, broker_evidence_authenticated=False,
            production_activated=False, requires_live_binding_recheck=True)
        for name in FILES:
            with (directory/name).open('r+b') as stream: os.fsync(stream.fileno())
        temporary = directory/'manifest.pending'
        with temporary.open('xb') as stream:
            stream.write(canonical(manifest)); stream.flush(); os.fsync(stream.fileno())
        os.link(temporary, directory/'complete.json')
        temporary.unlink()
        return manifest
    except BaseException:
        # Retain partial evidence for diagnosis; absence of complete.json is final.
        if not (directory/'complete.json').exists():
            (directory/'failed.json').write_bytes(canonical(dict(status='PREPARATION_FAILED_NOT_PUBLISHED')))
        raise


def verify_split_bundle(directory):
    directory = checked_path(directory)
    require(not (directory/'failed.json').exists(), 'SPLIT_BUNDLE_FAILED')
    manifest_path = checked_path(directory/'complete.json')
    require(manifest_path.is_file(), 'SPLIT_BUNDLE_INCOMPLETE')
    manifest = json.loads(manifest_path.read_bytes())
    require(manifest.get('schema') == 'SPLIT_PREPARATION_BUNDLE_V1'
            and manifest.get('status') == 'PREPARED_NOT_ACTIVATED'
            and manifest.get('production_activated') is False, 'SPLIT_BUNDLE_SCHEMA')
    require(set(manifest['files']) == set(FILES), 'SPLIT_BUNDLE_FILE_DOMAIN')
    for name in FILES:
        path = checked_path(directory/name)
        require(sha256(path.read_bytes()).hexdigest() == manifest['files'][name], 'SPLIT_BUNDLE_FILE_CHANGED')
    state = SplitStrategyAccountStore(directory/'account.sqlite3').read()
    require(state['revision'] == manifest['account_revision'] and state['account_id'] == manifest['account_id'],
            'SPLIT_BUNDLE_ACCOUNT_BINDING')
    risk = MonthlyPeakExitStore(directory/'risk.sqlite3').read(state['account_id'])
    require(sha256(canonical(risk)).hexdigest() == manifest['risk_state_sha256'], 'SPLIT_BUNDLE_RISK_BINDING')
    inputs = json.loads((directory/'inputs.json').read_bytes())
    require(inputs['action']['action_id'] == manifest['action_id']
            and inputs['target']['target_id'] == manifest['target_id']
            and inputs['expected_proposal_id'] == manifest['proposal_id'], 'SPLIT_BUNDLE_INPUT_BINDING')
    require(any(row['payload'] == inputs['action'] for row in state['events']), 'SPLIT_BUNDLE_ACTION_BINDING')
    transition = project_native_split(account_after=state, action_id=manifest['action_id'],
        risk_before=inputs['risk_before'], target=inputs['target'], expected_proposal_id=manifest['proposal_id'])
    require(transition['transition_id'] == manifest['transition_id'], 'SPLIT_BUNDLE_TRANSITION_BINDING')
    return manifest
