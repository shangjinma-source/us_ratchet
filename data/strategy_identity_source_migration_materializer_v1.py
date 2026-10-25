"""Prepare the current-security identity closure migration; never activate or run it."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4

from core.strategy_account_ledger import canonical, require
from data.strategy_daily_domain_policy_reader_v1 import REVIEW_SOURCES
from data.strategy_daily_dynamic_factory_v4 import FACTORY_SOURCES
from data.strategy_daily_session_capture import stamp
from data.strategy_bounded_source_gate_v1 import _no_links
from data.strategy_continuous32_target_decision import PROFILE_ID, VERSION
from scripts.register_quantity_v2_paper_protocol import safe_path


MIGRATION_SOURCES = {
    'data/strategy_daily_first_window_v3.py',
    'data/strategy_daily_dynamic_factory_v4.py',
    'scripts/run_daily_dynamic_source_v4.py',
    'scripts/run_local_dynamic_daily_sources_v4.ps1',
}

PARENTS = {
    'LATEST_DISPLAY_UNIFIED_PREPARATION_V10': 'base_v9',
    'SNAPSHOT_VALUATION_UNIFIED_PREPARATION_V9': 'base_v8',
    'OBSERVED_UNIFIED_PREPARATION_V8': 'base_v7',
    'SESSION_GUARDED_UNIFIED_PREPARATION_V7': 'base_v6',
}


def materialize_source_migration_chain(*, root, server_reference, upgrade_reference,
                                    application_reference, release_reference, new_source_reference,
                                    output_directory, clock, validate_sources):
    root = Path(root).absolute()
    observed = {}

    def read(reference, maximum=32*1024*1024):
        require(type(reference) is dict and set(reference) == {'path', 'sha256'},
                'POLICY_REFERENCE_FIELDS')
        path = safe_path(root, reference['path'])
        _no_links(path)
        with path.open('rb') as stream:
            raw = stream.read(maximum+1)
        require(len(raw) <= maximum and sha256(raw).hexdigest() == reference['sha256'],
                'POLICY_SOURCE_CHANGED')
        observed[reference['path']] = (deepcopy(reference), raw)
        return raw

    validate_sources()
    now = stamp(clock())
    chain = []
    reference = server_reference
    for schema, parent in PARENTS.items():
        document = json.loads(read(reference))
        require(document['schema'] == schema, 'POLICY_REQUIRES_COMPLETE_V10_CHAIN')
        chain.append(document)
        reference = document[parent]
    base = json.loads(read(reference))
    require(base['schema'] == 'UNIFIED_REVIEWED_DOMAIN_SERVER_PREPARATION_V6'
            and base['upgrade'] == upgrade_reference, 'POLICY_FRESH_UPGRADE_MISMATCH')
    chain.append(base)
    upgrade = json.loads(read(upgrade_reference))
    require(upgrade['schema'] == 'CONTINUOUS32_RESEARCH_UPGRADE_V1',
            'POLICY_UPGRADE_SCHEMA')
    application = json.loads(read(application_reference))
    release = json.loads(read(release_reference))
    require(application['schema'] == 'SERVER_DOMAIN_POLICY_APPLICATION_REVIEW_V1'
            and application['authorized'] is True
            and application['scope'] == 'COMPLETE_CURRENT_SESSION_DOMAIN'
            and application['release'] == release_reference,
            'POLICY_APPLICATION_NOT_REVIEWED')
    require(release['schema'] == 'SERVER_DAILY_POLICY_RELEASE_V1'
            and release['approved'] is True
            and release['scope'] == 'WEB_MANUAL_ADVICE_RULE_ONLY'
            and release['no_automatic_order_submission'] is True,
            'POLICY_RELEASE_NOT_REVIEWED')
    for document in (application, release):
        require(document['selector_profile'] == PROFILE_ID
                and document['selection_method'] == VERSION
                and type(document['continuous_iterations']) is int
                and document['continuous_iterations'] == 32, 'POLICY_PROFILE')
    require(stamp(application['authorized_at']) <= now
            and stamp(release['approved_at']) <= now
            and stamp(application['authorized_at']) <= stamp(application['valid_from'])
            < stamp(application['valid_until']) and now < stamp(application['valid_until']),
            'POLICY_REVIEW_TIME')
    daily = json.loads(read(base['daily_configuration']))
    evidence = daily['evidence']
    source_reference = dict(path=evidence['configuration_path'],
                            sha256=evidence['configuration_sha256'])
    old_source = json.loads(read(source_reference))
    source = json.loads(read(new_source_reference))
    require(old_source['schema'] == source['schema'] == 'SERVER_DYNAMIC_DAILY_SOURCE_V1'
            and old_source.get('first_window_review_version') == source.get('first_window_review_version') == 'CLOSED_AT_ORIGINAL_RECEIPT_V2'
            and old_source.get('official_time_policy') == source.get('official_time_policy') == 'REAL_WAIT_CHANNEL_MAX_1S_ITEMS_AT_NETWORK_RECEIPT_V1'
            and 'identity_closure_scope' not in old_source
            and source.get('identity_closure_scope') == 'CURRENT_SECURITY_REFERENCES_V1',
            'MIGRATION_FIRST_WINDOW_VERSION')
    old_fixed = deepcopy(old_source)
    new_fixed = deepcopy(source)
    for value in (old_fixed, new_fixed):
        value.pop('source_pins', None)
        value.pop('runs_root', None)
        value.pop('identity_closure_scope', None)
    require(old_fixed == new_fixed, 'MIGRATION_SOURCE_SCOPE_CHANGED')
    require(source['runs_root'] != old_source['runs_root'], 'MIGRATION_REQUIRES_NEW_RUNS_ROOT')
    destination = safe_path(root, source['runs_root'])
    _no_links(destination)
    require(destination != root and not destination.exists(), 'MIGRATION_REQUIRES_UNUSED_RUNS_ROOT')
    old_pins = {r['path']: r['sha256'] for r in old_source['source_pins']}
    new_pins = {r['path']: r['sha256'] for r in source['source_pins']}
    require(len(new_pins) == len(source['source_pins']) and FACTORY_SOURCES <= set(new_pins)
            and set(new_pins) == set(old_pins) | MIGRATION_SOURCES
            and all(new_pins.get(k) == v for k, v in old_pins.items()), 'MIGRATION_SOURCE_PINS')
    for pin in source['source_pins']:
        body = read(pin)
        if pin['path'] in FACTORY_SOURCES | MIGRATION_SOURCES:
            require(body == (Path(__file__).resolve().parents[1]/pin['path']).read_bytes(),
                    'MIGRATION_EXECUTING_SOURCE')
    old_application_reference = dict(path=evidence['review_configuration_path'],
                                    sha256=evidence['review_configuration_sha256'])
    old_application = json.loads(read(old_application_reference))
    require(old_application['source_configuration'] == source_reference
            and old_application['release'] == release_reference,
            'MIGRATION_ORIGINAL_APPLICATION_BINDING')
    old_application_fixed, new_application_fixed = deepcopy(old_application), deepcopy(application)
    for value in (old_application_fixed, new_application_fixed):
        value.pop('source_configuration', None)
        value.pop('code_pins', None)
    require(old_application_fixed == new_application_fixed, 'MIGRATION_AUTHORIZATION_CHANGED')
    old_review_pins = {r['path']: r['sha256'] for r in old_application['code_pins']}
    new_review_pins = {r['path']: r['sha256'] for r in application['code_pins']}
    require(len(new_review_pins) == len(application['code_pins'])
            and FACTORY_SOURCES <= set(new_review_pins)
            and set(new_review_pins) == set(old_review_pins) | MIGRATION_SOURCES
            and all(new_review_pins.get(k) == v for k, v in old_review_pins.items()),
            'MIGRATION_REVIEW_PINS')
    source_reference = new_source_reference
    require(application['source_configuration'] == source_reference
            and application['account_id'] == source['account_id']
            and application['calendar'] == source['calendar']
            and release['calendar_sha256'] == source['calendar']['sha256'],
            'POLICY_SOURCE_BINDING')
    read(source['calendar'])
    require(REVIEW_SOURCES <= {r['path'] for r in application['code_pins']},
            'POLICY_CODE_SCOPE')
    for pin in application['code_pins']:
        read(pin)
    for field in ('code_sha256', 'research_evidence_sha256'):
        for path, digest in release[field].items():
            read(dict(path=path, sha256=digest))
    for document in chain:
        for path, digest in document.get('source_pins', {}).items():
            read(dict(path=path, sha256=digest))
    final = safe_path(root, output_directory)
    _no_links(final)
    require(not final.exists(), 'POLICY_OUTPUT_EXISTS')
    daily = deepcopy(daily)
    daily.update(policy_execution_enabled=True, policy_id=release['policy_id'])
    daily['evidence'].update(
        configuration_path=new_source_reference['path'],
        configuration_sha256=new_source_reference['sha256'],
        review_configuration_path=application_reference['path'],
        review_configuration_sha256=application_reference['sha256'],
        release_path=release_reference['path'],
        trusted_release_sha256=release_reference['sha256'])
    outputs = [('daily.json', canonical(daily))]

    def output_reference(name, raw):
        return dict(path=(final/name).relative_to(root).as_posix(),
                    sha256=sha256(raw).hexdigest())

    child = output_reference(*outputs[0])
    for index in reversed(range(len(chain))):
        document = deepcopy(chain[index])
        field = 'daily_configuration' if index == len(chain)-1 else PARENTS[document['schema']]
        document[field] = child
        name = 'server.json' if index == 0 else f'server-level-{index}.json'
        raw = canonical(document)
        outputs.append((name, raw))
        child = output_reference(name, raw)
    receipt = dict(schema='SECURITY_IDENTITY_CLOSURE_MIGRATION_PREPARATION_V1',
                   status='PREPARED_NOT_ACTIVATED', server_reference=child,
                   original_server_reference=server_reference,
                   new_source_reference=new_source_reference,
                   upgrade_reference=upgrade_reference,
                   application_reference=application_reference,
                   release_reference=release_reference,
                   valid_from=application['valid_from'], valid_until=application['valid_until'],
                   prepared_at=now.isoformat(), account_mutated=False, target_mutated=False,
                   runtime_admission_still_required=True)
    outputs.append(('preparation.json', canonical(receipt)))
    final.parent.mkdir(parents=True, exist_ok=True)
    temporary = final.parent/('.'+final.name+'.preparing-'+uuid4().hex)
    temporary.mkdir()
    try:
        for name, raw in outputs:
            with (temporary/name).open('xb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        validate_sources()
        for pin, original in list(observed.values()):
            require(read(pin) == original, 'POLICY_SOURCE_CHANGED')
        require(now <= stamp(clock()) < stamp(application['valid_until']), 'POLICY_CLOCK_CHANGED')
        require(not final.exists(), 'POLICY_OUTPUT_EXISTS')
        require(not destination.exists(), 'MIGRATION_REQUIRES_UNUSED_RUNS_ROOT')
        temporary.rename(final)
    except BaseException:
        (temporary/'failed.json').write_bytes(canonical({'status': 'PREPARATION_FAILED'}))
        raise
    return receipt
