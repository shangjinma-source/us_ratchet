"""Explicit review of a new attempt after an unsaved failed decision.

This never restores or reconstructs the old selected decision.
"""
from hashlib import sha256
import json
from pathlib import Path
from datetime import datetime, timezone
from core.strategy_account_ledger import require
from data.strategy_bounded_source_gate_v1 import _no_links
from scripts.register_quantity_v2_paper_protocol import safe_path


def validate_recovery_review(*, root, reference, package=None, targets=None):
    root = Path(root)
    def read(ref, lines=False):
        require(type(ref) is dict and set(ref) == {'path', 'sha256'}, 'RECOVERY_REFERENCE')
        path = safe_path(root, ref['path'])
        _no_links(path)
        with path.open('rb') as stream:
            raw = stream.read(2*1024*1024+1)
        require(len(raw) <= 2*1024*1024 and sha256(raw).hexdigest() == ref['sha256'],
                'RECOVERY_SOURCE_CHANGED')
        return [json.loads(line) for line in raw.splitlines()] if lines else json.loads(raw)
    review = read(reference)
    require(review['schema'] == 'UNSAVED_UPGRADE_NEW_ATTEMPT_REVIEW_V1'
            and review['authorized'] is True
            and review['old_decision_saved'] is False
            and review['operation'] == 'NEW_SELECTION_NOT_RECOVERY_OF_OLD_DECISION',
            'RECOVERY_REVIEW_REQUIRED')
    reviewed = datetime.fromisoformat(review['reviewed_at'])
    require(reviewed.utcoffset() is not None and reviewed <= datetime.now(timezone.utc)
            and review['authorization_basis'] ==
            'EXISTING_USER_CONTINUE_AUTHORIZATION_AND_IMPLEMENTER_STORAGE_FIX_REVIEW',
            'RECOVERY_AUTHORITY_REQUIRED')
    old = read(review['failed_package'])
    terminal = read(review['failed_terminal'], lines=True)
    require(len(terminal) == 2 and terminal[0]['status'] == 'STARTED'
            and terminal[1]['status'] == 'FAILED_PRESERVED'
            and terminal[1]['error'] == 'UPGRADE_SOURCE_BUDGET'
            and all(row['mode'] == 'execute' and row['package_sha256'] ==
                    review['failed_package']['sha256'] for row in terminal),
            'RECOVERY_TERMINAL_BINDING')
    claim = read(review['failed_claim'])
    diagnosis = read(review['failure_diagnosis'])
    require(diagnosis['reason'] == 'UPGRADE_SOURCE_BUDGET'
            and diagnosis['claim_exists'] is True and diagnosis['prepared_exists'] is False
            and diagnosis['claim_sha256'] == review['failed_claim']['sha256'],
            'RECOVERY_DIAGNOSIS_BINDING')
    digest = review['failed_package']['sha256']
    claim_path = 'data/strategy_account/research_upgrades/'+digest+'/claim.json'
    require(review['failed_claim']['path'] == claim_path
            and claim['package_sha256'] == digest
            and claim['request']['event_id'] == old['upgrade_event_id']
            and claim['request']['previous_target_id'] == old['previous_target_id']
            and claim['account_state']['revision'] == old['account_revision'],
            'RECOVERY_CLAIM_BINDING')
    prepared = safe_path(root, 'data/strategy_account/research_upgrades/'+digest+'/prepared.json')
    _no_links(prepared)
    require(not prepared.exists(), 'RECOVERY_OLD_PREPARED_EXISTS')
    require(review['new_event_id'] != old['upgrade_event_id']
            and review['previous_target_id'] == old['previous_target_id'],
            'RECOVERY_NEW_EVENT_REQUIRED')
    if targets is not None:
        require(targets.operation(old['upgrade_event_id']) is None,
                'RECOVERY_OLD_EVENT_PUBLISHED')
    if package is not None:
        require(package['upgrade_event_id'] == review['new_event_id']
                and package['previous_target_id'] == review['previous_target_id']
                and package['account_revision'] == review['account_revision']
                and package['source_hashes'].get(reference['path']) == reference['sha256']
                and package['reviewed_training'] == old['reviewed_training']
                and package['upgraded_configuration'] == old['upgraded_configuration'],
                'RECOVERY_NEW_PACKAGE_BINDING')
    return review
