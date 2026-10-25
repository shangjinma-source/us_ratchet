"""Create-only current-account rebind of an externally reviewed upgrade template.

No market fetch, selection, target append or account write. A complete output
directory is renamed into place only after final live snapshot/source checks.
"""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import canonical, require
from data.strategy_bounded_source_gate_v1 import _no_links
from data.strategy_continuous32_target_decision import PROFILE_ID
from data.strategy_profiled_runtime_archive import require_archived_configuration
from scripts.register_quantity_v2_paper_protocol import safe_path


def materialize_current_upgrade(*, monthly, template_reference, new_event_id,
                                output_directory, server_reference, validate_sources):
    root = Path(monthly.root).absolute()
    require(type(new_event_id) is str and 0 < len(new_event_id) <= 128,
            'UPGRADE_EVENT_INVALID')
    def read(ref):
        require(type(ref) is dict and set(ref) == {'path', 'sha256'}, 'UPGRADE_REFERENCE_FIELDS')
        path = safe_path(root, ref['path'])
        _no_links(path)
        with path.open('rb') as stream:
            raw = stream.read(1024*1024+1)
        require(len(raw) <= 1024*1024 and sha256(raw).hexdigest() == ref['sha256'],
                'UPGRADE_SOURCE_CHANGED')
        return raw, json.loads(raw)
    validate_sources()
    template_raw, template = read(template_reference)
    server_raw, server = read(server_reference)
    server_chain = [(server_reference, server_raw)]
    base_fields = {
        'LATEST_DISPLAY_UNIFIED_PREPARATION_V10': 'base_v9',
        'SNAPSHOT_VALUATION_UNIFIED_PREPARATION_V9': 'base_v8',
        'OBSERVED_UNIFIED_PREPARATION_V8': 'base_v7',
        'SESSION_GUARDED_UNIFIED_PREPARATION_V7': 'base_v6'}
    for _ in range(5):
        if server.get('schema') == 'UNIFIED_REVIEWED_DOMAIN_SERVER_PREPARATION_V6':
            break
        require(server.get('schema') in base_fields, 'UPGRADE_SERVER_SCHEMA')
        reference = server[base_fields[server['schema']]]
        raw, server = read(reference)
        server_chain.append((reference, raw))
    require(server.get('schema') == 'UNIFIED_REVIEWED_DOMAIN_SERVER_PREPARATION_V6'
            and server.get('upgrade') == template_reference, 'UPGRADE_SERVER_TEMPLATE_MISMATCH')
    require(template['schema'] == 'CONTINUOUS32_RESEARCH_UPGRADE_V1'
            and template['purpose'] == 'EXPLICIT_SAME_MONTH_RESEARCH_VERSION_UPGRADE_NOT_MONTHLY_PUBLICATION',
            'UPGRADE_TEMPLATE_SCHEMA')
    require(new_event_id != template['upgrade_event_id'], 'UPGRADE_NEW_EVENT_REQUIRED')
    final = safe_path(root, output_directory)
    _no_links(final)
    require(not final.exists(), 'UPGRADE_OUTPUT_EXISTS')
    with monthly.snapshot_operation() as active:
        state = deepcopy(monthly.accounts.read())
        target = deepcopy(monthly.current())
        snapshot = deepcopy(dict(active))
        require(state is not None and target is not None, 'UPGRADE_CURRENT_ACCOUNT_TARGET_REQUIRED')
        require(target['target_id'] == template['previous_target_id'],
                'UPGRADE_REVIEWED_TARGET_CHANGED')
        require(target['payload']['decision']['payload']['input_binding'].get('selector_profile') is None,
                'UPGRADE_REQUIRES_ORIGINAL_TARGET')
        require(monthly.targets.operation(new_event_id) is None, 'UPGRADE_EVENT_ALREADY_USED')
        now = monthly.clock()
        require(now.utcoffset() is not None, 'UPGRADE_AWARE_CLOCK')
        require(template['target_month'] == now.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m')
                == target['payload']['target_month'], 'UPGRADE_MONTH_EXPIRED')
        expected_snapshot = dict(template['base_snapshot'],
            archive_path=template['upgrade_archive']['path'],
            archive_sha256=template['upgrade_archive']['sha256'])
        require(snapshot == expected_snapshot, 'UPGRADE_SNAPSHOT_CHANGED')
        _, original = monthly._for_target(target)
        require(sha256(canonical(original)).hexdigest() == template['original_configuration_sha256'],
                'UPGRADE_ORIGINAL_CONFIGURATION_CHANGED')
        require(template['reviewed_training'] == dict(path=original['training_manifest'],
            sha256=original['training_sha256'], closed_at=original['training_closed_at']),
            'UPGRADE_TRAINING_BINDING')
        upgraded_raw, upgraded = read(template['upgraded_configuration'])
        require(upgraded['schema'] == 'REAL_STRATEGY_CONTINUOUS32_RUNTIME_V1'
                and upgraded['selector_profile'] == PROFILE_ID, 'UPGRADE_PROFILE_REQUIRED')
        for key in ('target_month', 'training_manifest', 'training_sha256',
                    'training_closed_at', 'identity_manifest', 'identity_sha256'):
            require(upgraded[key] == original[key], 'UPGRADE_SAVED_DATA_CHANGED')
        require_archived_configuration(root=root, archive_path=monthly.archive_path,
            archive_sha256=monthly.archive_sha256, configuration=upgraded)
        monthly._runtime(upgraded).selection._pins()
        for name, digest in template['source_hashes'].items():
            path = safe_path(root, name)
            _no_links(path)
            require(sha256(path.read_bytes()).hexdigest() == digest, 'UPGRADE_SOURCE_CHANGED')
        package = deepcopy(template)
        package.update(account_revision=state['revision'],
                       previous_target_id=target['target_id'], upgrade_event_id=new_event_id)
        package_raw = canonical(package)
        package_digest = sha256(package_raw).hexdigest()
        upgrade_reference = dict(path=(final/'upgrade.json').relative_to(root).as_posix(),
                                 sha256=package_digest)
        server_outputs = []
        child_reference = None
        for index in reversed(range(len(server_chain))):
            document = json.loads(server_chain[index][1])
            if child_reference is None:
                document['upgrade'] = upgrade_reference
            else:
                document[base_fields[document['schema']]] = child_reference
            name = 'server.json' if index == 0 else f'server-level-{index}.json'
            raw = canonical(document)
            server_outputs.append((name, raw))
            child_reference = dict(path=(final/name).relative_to(root).as_posix(),
                                   sha256=sha256(raw).hexdigest())
        # Server configuration is a review anchor, not silently rewritten.
        receipt = dict(schema='CURRENT_UPGRADE_PREPARATION_V1',
            status='PREPARED_NOT_EXECUTED', reviewed_template=template_reference,
            current_server_reference=server_reference,
            proposed_server_upgrade_reference=upgrade_reference,
            proposed_server_reference=child_reference,
            requires_new_server_configuration_review=True,
            account_revision=state['revision'], previous_target_id=target['target_id'],
            upgrade_event_id=new_event_id, prepared_at=now.isoformat(),
            selection_started=False, account_mutated=False, target_mutated=False)
        final.parent.mkdir(parents=True, exist_ok=True)
        temporary = final.parent/('.'+final.name+'.preparing-'+uuid4().hex)
        temporary.mkdir(exist_ok=False)
        try:
            for name, raw in [('upgrade.json', package_raw), *server_outputs,
                              ('preparation.json', canonical(receipt))]:
                with (temporary/name).open('xb') as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
            validate_sources()
            require(read(template_reference)[0] == template_raw
                    and read(server_reference)[0] == server_raw
                    and read(template['upgraded_configuration'])[0] == upgraded_raw,
                    'UPGRADE_SOURCE_CHANGED')
            require(all(read(ref)[0] == raw for ref, raw in server_chain), 'UPGRADE_SERVER_CHAIN_CHANGED')
            monthly._runtime(upgraded).selection._pins()
            for name, digest in template['source_hashes'].items():
                path = safe_path(root, name)
                _no_links(path)
                require(sha256(path.read_bytes()).hexdigest() == digest, 'UPGRADE_SOURCE_CHANGED')
            require(monthly.accounts.read() == state and monthly.current() == target
                    and monthly.targets.operation(new_event_id) is None, 'UPGRADE_SNAPSHOT_CHANGED')
            finished = monthly.clock()
            require(finished >= now and finished.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m')
                    == package['target_month'], 'UPGRADE_PREPARATION_TIME_CHANGED')
            complete_raw = canonical(dict(status='PREPARED_NOT_EXECUTED',
                package_sha256=package_digest,
                proposed_server_reference=child_reference,
                preparation_sha256=sha256(canonical(receipt)).hexdigest(),
                finished_at=finished.isoformat()))
            with (temporary/'complete.json').open('xb') as stream:
                stream.write(complete_raw)
                stream.flush()
                os.fsync(stream.fileno())
            validate_sources()
            require(all(read(ref)[0] == raw for ref, raw in server_chain),
                    'UPGRADE_SERVER_CHAIN_CHANGED')
            require(dict(monthly._snapshot_provider()) == snapshot, 'UPGRADE_SNAPSHOT_CHANGED')
            require(monthly.accounts.read() == state and monthly.current() == target,
                    'UPGRADE_SNAPSHOT_CHANGED')
            require(not final.exists(), 'UPGRADE_OUTPUT_EXISTS')
            temporary.rename(final)
        except BaseException:
            with (temporary/'failed.json').open('xb') as stream:
                stream.write(canonical(dict(status='PREPARATION_FAILED_NOT_PUBLISHED')))
            raise
    return dict(receipt, package_reference=receipt['proposed_server_upgrade_reference'],
                output_directory=final.relative_to(root).as_posix())
