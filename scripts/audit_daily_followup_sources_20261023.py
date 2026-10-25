"""Read-only inventory of original advice evidence; does not admit capture."""
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from data.strategy_daily_advice_journal_v1 import DailyAdviceJournalV1
from data.strategy_advice_followup_plan_v1 import plan_journal_page
from data.strategy_daily_explanations_v1 import explain_preview
from core.strategy_account_difference import timestamp
from data.strategy_followup_price_basis_v1 import review_price_basis


def audit(root):
    root = Path(root).resolve()
    journal = DailyAdviceJournalV1(root/'data/strategy_account/daily_advice_v1.sqlite3')
    calendar = (root/'research_contracts/daily_calendar_2026_extension_v1/calendar.candidate.json').read_bytes()
    calendar_hash = sha256(calendar).hexdigest()
    assert calendar_hash == '1440d82ecc956baab15df4b49da444e4878459e353cf7c280dd5d3dcf2a109af'
    now = datetime.now(timezone.utc)
    with sqlite3.connect(journal.path.as_uri()+'?mode=ro', uri=True) as database:
        records = database.execute('SELECT event_id,account_id,body,digest FROM advice_events ORDER BY sequence').fetchall()
    assert len(records) <= 10000, 'AUDIT_BOUND_EXCEEDED'
    plans = {}
    for account in sorted({row[1] for row in records}):
        cursor = 0
        for _ in range(101):
            page = plan_journal_page(journal=journal, account_id=account, calendar_bytes=calendar,
                calendar_sha256=calendar_hash, now=now, after=cursor, limit=100)
            plans.update({item['event_id']: item for item in page['items']})
            cursor = page['next_cursor']
            if len(page['items']) < 100:
                break
        else:
            raise ValueError('AUDIT_BOUND_EXCEEDED')
    rows = []
    def read_reference(path, digest):
        path = Path(path)
        if not path.is_absolute():
            path = root/path
        assert path.resolve().is_relative_to(root/'data/strategy_account'), 'REFERENCE_OUTSIDE_ACCOUNT_EVIDENCE'
        assert not path.is_symlink() and not any(parent.is_symlink() for parent in path.parents), 'REFERENCE_SYMLINK'
        assert path.stat().st_size <= 32*1024*1024, 'REFERENCE_TOO_LARGE'
        raw = path.read_bytes()
        assert sha256(raw).hexdigest() == digest, 'REFERENCE_HASH_MISMATCH'
        return json.loads(raw)
    for event_id, account, raw, digest in records:
        plan = plans[event_id]
        if plan['status'] != 'PLANNED_NOT_CAPTURE_ADMITTED':
            continue
        row = dict(event_id=event_id, due=sum(o['status']=='DUE' for o in plan['observations']),
                   capture_admitted=False)
        try:
            assert sha256(raw).hexdigest() == digest, 'EVENT_CHANGED'
            event = json.loads(raw)
            response = event['response']
            reference = response['execution_binding']
            binding = read_reference(reference['path'], reference['sha256'])
            assert binding['schema']=='DAILY_EXECUTION_PROJECTION_V1', 'BINDING_SCHEMA'
            assert binding['account_revision']==event['account_revision'], 'BINDING_REVISION'
            assert binding['base_target_id']==event['target_id']==reference['base_target_id'], 'BINDING_TARGET'
            assert binding['base_decision_id']==reference['base_decision_id'], 'BINDING_DECISION'
            assert binding['effective_target_quantities']==response['effective_target_quantities'], 'BINDING_QUANTITIES'
            archive = response['evidence_archive']
            assert binding['evidence_id']==reference['evidence_id']==archive['receipt_sha256'], 'BINDING_EVIDENCE'
            assert binding['signal']['account_id']==account, 'BINDING_ACCOUNT'
            assert binding['signal']['evidence_archive']==archive, 'BINDING_ARCHIVE'
            receipt_path = Path(archive['receipt_path'])
            receipt = read_reference(receipt_path, archive['receipt_sha256'])
            # Integrity/recomputation only. A path in a saved event is not policy authorization.
            archive_root = receipt_path.parent.parent
            explain_preview(response, archive_root=archive_root, policy_id=binding['policy_id'])
            source_files = {name:(receipt_path.parent/'sources'/(pin+'.bin')).read_bytes()
                            for name,pin in receipt['source_sha256'].items()}
            assert all(sha256(body).hexdigest()==receipt['source_sha256'][name]
                       for name,body in source_files.items()), 'PRICE_SOURCE_CHANGED'
            price_basis = review_price_basis(json.loads(source_files[receipt['normalized_inputs_path']]), source_files)
            recorded_root = event['policy_references']['evidence_references']['archive_root']
            evidence = event['policy_references']['evidence_references']
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
            row.update(status='ARCHIVE_INTEGRITY_AND_TARGET_RECOMPUTED',
                price_basis=price_basis,
                recorded_policy_archive_root=recorded_root,
                actual_archive_root=str(archive_root.relative_to(root)),
                policy_archive_root_matches=(root/recorded_root).resolve()==archive_root.resolve(),
                authorized_review_archive_root_matches=True,
                archive_root_semantics='RAW_AND_REVIEWED_ARCHIVES_ARE_SEPARATE',
                remaining='FULL_EXECUTION_SOURCE_REVIEW_REQUIRED')
        except (AssertionError, ValueError, KeyError, TypeError, OSError) as error:
            row.update(status='SOURCE_REVIEW_BLOCKED', reason=str(error))
        rows.append(row)
    return dict(observed_at=now.isoformat(), rows=rows, statuses=dict(Counter(r['status'] for r in rows)),
        policy_archive_root_mismatches=sum(r.get('policy_archive_root_matches') is False for r in rows),
        capture_admitted=False, account_writes=False, network_calls=0)


if __name__ == '__main__':
    result = audit(Path.cwd())
    output = Path('tmp/current_daily_followup_source_audit_20261023_v4.json')
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({key: value for key,value in result.items() if key!='rows'}, ensure_ascii=False))
