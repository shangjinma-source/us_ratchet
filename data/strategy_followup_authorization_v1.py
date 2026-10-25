"""Original domain-policy authorization checks shared by follow-up reviewers."""
import json
from pathlib import Path
from hashlib import sha256
from core.strategy_account_difference import timestamp


def review_authorization(*,root,event,evidence,receipt,receipt_path,read_reference):
    account=event['account_id'];archive_root=receipt_path.parent.parent
    authorization_ref = receipt['policy_application_authorization']
    assert authorization_ref['sha256'] == evidence['review_configuration_sha256'], 'AUTHORIZATION_JOURNAL_BINDING'
    assert receipt['source_sha256'][authorization_ref['path']] == authorization_ref['sha256'], 'AUTHORIZATION_SOURCE_BINDING'
    authorization = read_reference(receipt_path.parent/'sources'/(authorization_ref['sha256']+'.bin'), authorization_ref['sha256'])
    configuration_path = (root/evidence['review_configuration_path']).resolve()
    assert configuration_path.is_relative_to(root/'research_contracts'), 'AUTHORIZATION_CONFIG_SCOPE'
    configuration_bytes = configuration_path.read_bytes()
    assert sha256(configuration_bytes).hexdigest()==authorization_ref['sha256'], 'AUTHORIZATION_CONFIGURATION_CHANGED'
    assert json.loads(configuration_bytes)==authorization, 'AUTHORIZATION_CONTENT_MISMATCH'
    assert authorization['schema']=='SERVER_DOMAIN_POLICY_APPLICATION_REVIEW_V1' and authorization['authorized'] is True, 'AUTHORIZATION_SCHEMA'
    assert authorization['account_id']==account, 'AUTHORIZATION_ACCOUNT'
    assert authorization['source_configuration']==dict(path=evidence['configuration_path'],sha256=evidence['configuration_sha256']), 'AUTHORIZATION_SOURCE_CONFIGURATION'
    assert authorization['release']['sha256']==evidence['trusted_release_sha256']==receipt['release_sha256'], 'AUTHORIZATION_RELEASE'
    assert (root/authorization['archive_root']).resolve()==archive_root.resolve(), 'AUTHORIZED_ARCHIVE_ROOT_MISMATCH'
    application_ref = receipt['policy_application_event']
    assert receipt['source_sha256'][application_ref['path']]==application_ref['sha256'], 'APPLICATION_SOURCE_BINDING'
    application = read_reference(receipt_path.parent/'sources'/(application_ref['sha256']+'.bin'), application_ref['sha256'])
    assert application['schema']=='DOMAIN_POLICY_APPLICATION_EVENT_V1', 'APPLICATION_SCHEMA'
    assert application['authorization_sha256']==authorization_ref['sha256'] and application['authorization_id']==authorization['authorization_id'], 'APPLICATION_AUTHORIZATION'
    assert application['source_configuration_sha256']==evidence['configuration_sha256'], 'APPLICATION_SOURCE_CONFIGURATION'
    assert application['release_sha256']==receipt['release_sha256'], 'APPLICATION_RELEASE'
    assert application['account_id']==account and application['account_revision']==event['account_revision'] and application['target_id']==event['target_id'], 'APPLICATION_ACCOUNT_TARGET'
    assert application['session']==receipt['execution_session']['date'], 'APPLICATION_SESSION'
    assert timestamp(authorization['authorized_at'])<=timestamp(authorization['valid_from'])<=timestamp(application['reviewed_at'])<=timestamp(event['generated_at'])<timestamp(authorization['valid_until']), 'APPLICATION_TIME'
    return dict(authorized_review_archive_root_matches=True)
