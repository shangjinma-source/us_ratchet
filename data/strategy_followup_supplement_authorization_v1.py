"""Verify archived supplementation authority without changing advice or sources."""
import json
from hashlib import sha256
from core.strategy_account_ledger import require
from core.strategy_account_difference import timestamp


def review_supplement_authorization(*, root, event, evidence, receipt, receipt_path, read_reference):
    pins = receipt['source_sha256']
    control_names = [name for name in pins if name.startswith('supplement-controls/')]
    event_names = [name for name in pins if name.startswith('supplement-events/')]
    require(len(control_names) == len(event_names) == 1, 'SUPPLEMENT_AUTHORITY_UNIQUE')
    def source(name):
        return read_reference(receipt_path.parent/'sources'/(pins[name]+'.bin'),pins[name])
    control_name, event_name = control_names[0], event_names[0]
    control, application = source(control_name), source(event_name)
    control_hash, application_hash = pins[control_name], pins[event_name]
    require(control_name == 'supplement-controls/'+control_hash+'.json' and
        event_name == 'supplement-events/'+application_hash+'.json', 'SUPPLEMENT_AUTHORITY_NAMES')
    require(control_hash == evidence['review_configuration_sha256'] == application['authorization_sha256'],
        'SUPPLEMENT_AUTHORITY_BINDING')
    path = (root/evidence['review_configuration_path']).resolve()
    require(path.is_relative_to(root/'research_contracts'), 'SUPPLEMENT_AUTHORITY_SCOPE')
    raw = path.read_bytes()
    require(sha256(raw).hexdigest() == control_hash and json.loads(raw) == control,
        'SUPPLEMENT_AUTHORITY_CHANGED')
    require(control['schema'] == 'SERVER_DOMAIN_POLICY_APPLICATION_REVIEW_V1' and
        control['authorized'] is True and control['account_id'] == event['account_id'] and
        control['monthly_supplement']['authorized'] is True and
        control['monthly_supplement']['schema'] == 'CURRENT_SESSION_MONTHLY_SUPPLEMENT_V1',
        'SUPPLEMENT_AUTHORITY_INVALID')
    require(control['source_configuration'] == dict(path=evidence['configuration_path'],
        sha256=evidence['configuration_sha256']) and
        control['release']['sha256'] == evidence['trusted_release_sha256'] == receipt['release_sha256'],
        'SUPPLEMENT_AUTHORITY_RELEASE')
    require((root/control['archive_root']).resolve() == receipt_path.parent.parent.resolve(),
        'SUPPLEMENT_AUTHORITY_ARCHIVE')
    expected = dict(account_id=event['account_id'],account_revision=event['account_revision'],
        target_id=event['target_id'],session=receipt['execution_session']['date'])
    require(application['binding'] == expected, 'SUPPLEMENT_APPLICATION_BINDING')
    parents = receipt['aggregate_parents']
    require(len(parents) == len(application['packets']) and
        {row['security_id'] for row in parents} == set(application['packets']),
        'SUPPLEMENT_APPLICATION_DOMAIN')
    for row in parents:
        require(pins[row['path']] == row['sha256'], 'SUPPLEMENT_PARENT_HASH')
        parent = source(row['path']); review = parent['policy_binding_review']
        sid = row['security_id']
        require(parent['account_id'] == event['account_id'] and
            parent['release_sha256'] == receipt['release_sha256'] and
            parent['execution_session'] == receipt['execution_session'], 'SUPPLEMENT_PARENT_BINDING')
        require(review['schema'] == 'INITIAL_DOMAIN_POLICY_REVIEW_V1' and
            review['event_id'] == application_hash and review['security_id'] == sid and
            review['release_sha256'] == receipt['release_sha256'] and
            review['original_receipt_sha256'] == application['packets'][sid],
            'SUPPLEMENT_PARENT_REVIEW')
        original_name = 'policy-originals/'+application['packets'][sid]+'.json'
        require(pins[original_name] == application['packets'][sid], 'SUPPLEMENT_ORIGINAL_HASH')
        source(original_name)
        require(timestamp(control['authorized_at']) <= timestamp(control['valid_from']) <=
            timestamp(review['reviewed_at']) <= timestamp(receipt['available_at']) <=
            timestamp(event['generated_at']) < timestamp(control['valid_until']),
            'SUPPLEMENT_REVIEW_TIME')
    return dict(status='SUPPLEMENT_AUTHORIZATION_CHECKED', account_writes=False, network_calls=0)
