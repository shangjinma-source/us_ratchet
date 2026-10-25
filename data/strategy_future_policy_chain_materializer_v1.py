"""Prepare a reviewed future-policy V10 chain; never activate or run it."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4

from core.strategy_account_ledger import canonical, require
from data.strategy_daily_domain_policy_reader_v1 import REVIEW_SOURCES
from data.strategy_daily_session_capture import stamp
from data.strategy_bounded_source_gate_v1 import _no_links
from data.strategy_continuous32_target_decision import PROFILE_ID, VERSION
from scripts.register_quantity_v2_paper_protocol import safe_path


PARENTS = {
    'LATEST_DISPLAY_UNIFIED_PREPARATION_V10': 'base_v9',
    'SNAPSHOT_VALUATION_UNIFIED_PREPARATION_V9': 'base_v8',
    'OBSERVED_UNIFIED_PREPARATION_V8': 'base_v7',
    'SESSION_GUARDED_UNIFIED_PREPARATION_V7': 'base_v6',
}


def materialize_future_policy_chain(*, root, server_reference, upgrade_reference,
                                    application_reference, release_reference,
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
    source = json.loads(read(source_reference))
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
    receipt = dict(schema='FUTURE_POLICY_CHAIN_PREPARATION_V1',
                   status='PREPARED_NOT_ACTIVATED', server_reference=child,
                   original_server_reference=server_reference,
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
        temporary.rename(final)
    except BaseException:
        (temporary/'failed.json').write_bytes(canonical({'status': 'PREPARATION_FAILED'}))
        raise
    return receipt
