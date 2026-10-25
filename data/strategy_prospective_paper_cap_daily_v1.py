"""Reviewed paper evidence to cap/exit projection; no order admission.

The legacy verifier is used only for its receipt/calendar/unit admission.
Its SMA target is discarded, never layered onto cap/exit. The registered
descriptor must also contain an explicit cap projection release.
"""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from core.strategy_account_ledger import canonical
from data.strategy_paper_application_descriptor_v1 import stamp, require
from data.strategy_prospective_paper_daily_v1 import verify_prospective_daily, CODE_PATHS as DAILY_PINS
from data.strategy_prospective_paper_exit_packet_v1 import apply_paper_exit_packet, CODE_PATHS as EXIT_PINS
from data.strategy_monthly_supplement_capture import restore_reviewed_monthly_history

CODE_PATHS = DAILY_PINS | EXIT_PINS | {'data/strategy_prospective_paper_cap_daily_v1.py',
                                    'data/strategy_monthly_supplement_capture.py'}


def project_paper_cap_daily(*, daily_arguments, risk_store, cap_release_path):
    args = deepcopy(daily_arguments)
    admitted = verify_prospective_daily(**args)
    descriptor_args = args['authority']['descriptor_arguments']
    descriptor = json.loads(descriptor_args['descriptor_bytes'])
    require(CODE_PATHS <= set(descriptor['code_sha256']), 'PAPER_CAP_DAILY_CODE_SCOPE')
    raw = descriptor_args['source_bytes'][cap_release_path]
    require(sha256(raw).hexdigest() == descriptor['source_sha256'][cap_release_path],
            'PAPER_CAP_RELEASE_CHANGED')
    release = json.loads(raw)
    require(release.get('schema') == 'PAPER_CAP_EXIT_PROJECTION_RELEASE_V1'
            and release.get('policy_id') == 'MONTHLY_CAP50_EXIT20'
            and release.get('approved') is True
            and release.get('orders_allowed') is False
            and stamp(release['approved_at']) <= stamp(args['now']),
            'PAPER_CAP_PROJECTION_RELEASE_REQUIRED')
    if admitted.get('signal') is None:
        return dict(status=admitted['status'], projection=None, orders_created=False)
    receipt = json.loads(args['receipt_bytes'])
    inputs = json.loads(args['files'][receipt['normalized_inputs_path']])
    binding = args['selection_result']['payload']['input_binding']
    namespace = 'paper-cap-exit:' + sha256(canonical(dict(
        account_id=binding['account_id'], registration=binding['registration_sha256'],
        descriptor=binding['paper_application_sha256']))).hexdigest()
    previous = risk_store.read(namespace)
    month = args['selection_result']['payload']['target_month']
    same_month = previous is not None and previous.get('target_month') == month
    decision = previous['decision_date'] if same_month else datetime.fromisoformat(
        binding['valuation_at']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
    if decision > inputs['signal_date']:
        return dict(status='WAIT_FIRST_CONFIGURATION_CLOSE', projection=None, orders_created=False)
    if receipt.get('monthly_history_inputs') or receipt.get('full_domain_inputs_path'):
        inputs = restore_reviewed_monthly_history(receipt=receipt, files=args['files'],
                                                  decision_date=decision)
    for history in inputs['histories'].values():
        history['closes'] = [row for row in history['closes']
                             if decision <= row['date'] <= inputs['signal_date']]
    result = apply_paper_exit_packet(selection_result=args['selection_result'],
        selection_arguments=args['selection_arguments'], inputs=inputs,
        risk_store=risk_store, decision_date=decision,
        expected_previous_session=previous['session_date'] if previous else None,
        authorized_monthly_reset=decision if previous and not same_month else None)
    return dict(status='PAPER_CAP_EXIT_PROJECTION_READY', projection=result,
                source_receipt_sha256=args['trusted_receipt_sha256'],
                release_sha256=sha256(raw).hexdigest(), orders_created=False,
                automatic_acceptance_allowed=False,
                source_truth=admitted['source_truth'])
