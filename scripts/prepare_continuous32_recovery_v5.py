"""Create reviewed new-attempt materials only; never capture or select."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from core.strategy_account_ledger import canonical, require, replay, apply_event
from data.strategy_unified_server_preparation_v10 import build_unified_server_preparation_v10
from data.strategy_upgrade_recovery_materializer_v1 import materialize_recovery_upgrade
from data.strategy_upgrade_recovery_review_v1 import validate_recovery_review
from data.strategy_bounded_source_gate_v1 import _no_links
from scripts.register_quantity_v2_paper_protocol import safe_path


def validate_cash_only_continuation(previous, current):
    require(previous['account_id'] == current['account_id']
            and current['events'][:len(previous['events'])] == previous['events'],
            'RECOVERY_LEDGER_PREFIX_CHANGED')
    rebuilt = replay(previous['account_id'], [row['payload'] for row in previous['events']])
    require(rebuilt == previous, 'RECOVERY_OLD_STATE_INVALID')
    suffix = current['events'][len(previous['events']):]
    for row in suffix:
        require(row['payload']['kind'] == 'CASH_CONFIRM', 'RECOVERY_NON_CASH_CHANGE')
        rebuilt, effect = apply_event(rebuilt, row['payload'], expected_revision=rebuilt['revision'])
        require(effect == row['effect'], 'RECOVERY_LEDGER_EFFECT_CHANGED')
    require(rebuilt == current and previous['shares'] == current['shares']
            and previous['orders'] == current['orders']
            and previous['holdings_revision'] == current['holdings_revision'],
            'RECOVERY_HOLDINGS_OR_ORDERS_CHANGED')
    return dict(previous_revision=previous['revision'], current_revision=current['revision'],
                cash_confirmation_count=len(suffix),
                semantics='ONLY_REPLAY_VERIFIED_CASH_CONFIRM_SUFFIX')


def prepare(*, root, server_reference, failed_package_reference,
            diagnosis_reference, failed_terminal_reference, new_event_id, output_directory):
    root = Path(root)
    def read(reference):
        path = safe_path(root, reference['path'])
        _no_links(path)
        with path.open('rb') as stream:
            raw = stream.read(2*1024*1024+1)
        require(len(raw) <= 2*1024*1024 and sha256(raw).hexdigest() == reference['sha256'],
                'RECOVERY_SOURCE_CHANGED')
        return json.loads(raw)
    old = read(failed_package_reference)
    diagnosis = read(diagnosis_reference)
    prepared = build_unified_server_preparation_v10(root=root,
        configuration_path=server_reference['path'],
        configuration_sha256=server_reference['sha256'])
    monthly = prepared['monthly']
    with monthly.snapshot_operation():
        state, target = monthly.accounts.read(), monthly.current()
        require(target['target_id'] == old['previous_target_id'], 'RECOVERY_STALE_SNAPSHOT')
        claim_relative = ('data/strategy_account/research_upgrades/' +
                          failed_package_reference['sha256'] + '/claim.json')
        claim_path = safe_path(root, claim_relative)
        _no_links(claim_path)
        claim_raw = claim_path.read_bytes()
        claim_digest = sha256(claim_raw).hexdigest()
        require(claim_digest == diagnosis['claim_sha256'], 'RECOVERY_CLAIM_BINDING')
        claim = json.loads(claim_raw)
        require(claim['account_state']['revision'] == old['account_revision'],
                'RECOVERY_CLAIM_BINDING')
        cash_continuation = validate_cash_only_continuation(claim['account_state'], state)
        review = dict(schema='UNSAVED_UPGRADE_NEW_ATTEMPT_REVIEW_V1',
            authorized=True, reviewed_at=datetime.now(timezone.utc).isoformat(),
            authorization_basis='EXISTING_USER_CONTINUE_AUTHORIZATION_AND_IMPLEMENTER_STORAGE_FIX_REVIEW',
            old_decision_saved=False, operation='NEW_SELECTION_NOT_RECOVERY_OF_OLD_DECISION',
            failed_package=failed_package_reference, failure_diagnosis=diagnosis_reference,
            failed_terminal=failed_terminal_reference,
            failed_claim=dict(path=claim_relative, sha256=claim_digest),
            previous_target_id=target['target_id'], account_revision=state['revision'],
            new_event_id=new_event_id, cash_only_continuation=cash_continuation)
        review_path = safe_path(root, output_directory+'.review.json')
        _no_links(review_path)
        review_raw = canonical(review)
        review_path.parent.mkdir(parents=True, exist_ok=True)
        with review_path.open('xb') as stream:
            stream.write(review_raw)
        reference = dict(path=review_path.relative_to(root).as_posix(),
                         sha256=sha256(review_raw).hexdigest())
        validate_recovery_review(root=root, reference=reference, targets=monthly.targets)
    return materialize_recovery_upgrade(monthly=monthly,
        template_reference=failed_package_reference, new_event_id=new_event_id,
        output_directory=output_directory, server_reference=server_reference,
        recovery_reference=reference, validate_sources=prepared['validate_code'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'server-path', 'server-sha256', 'failed-package-path',
                 'failed-package-sha256', 'diagnosis-path', 'diagnosis-sha256',
                 'failed-terminal-path', 'failed-terminal-sha256',
                 'new-event-id', 'output-directory', 'receipt-path'):
        parser.add_argument('--'+name, required=True)
    args = parser.parse_args()
    receipt = safe_path(Path(args.root), args.receipt_path)
    _no_links(receipt)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    with receipt.open('x', encoding='utf8') as stream:
        result = prepare(root=args.root,
            server_reference=dict(path=args.server_path, sha256=args.server_sha256),
            failed_package_reference=dict(path=args.failed_package_path, sha256=args.failed_package_sha256),
            diagnosis_reference=dict(path=args.diagnosis_path, sha256=args.diagnosis_sha256),
            failed_terminal_reference=dict(path=args.failed_terminal_path, sha256=args.failed_terminal_sha256),
            new_event_id=args.new_event_id, output_directory=args.output_directory)
        json.dump(result, stream)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
