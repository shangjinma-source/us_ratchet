"""Pure research arithmetic for externally reviewed entitlements and payments.

No source admission, entitlement inference, account mutation or registration.
Payment records must be supplied by a future separately reviewed adapter.
"""
from fractions import Fraction
from datetime import datetime
import re
from core.strategy_account_ledger import require


def _time(value):
    result = datetime.fromisoformat(value)
    require(result.tzinfo is not None, 'DIVIDEND_TIMEZONE_REQUIRED')
    return result


def _amount(value):
    # Binary floats and booleans are not exact monetary evidence.
    require(type(value) in (str, int, Fraction), 'DIVIDEND_EXACT_AMOUNT_REQUIRED')
    return Fraction(value)


def project(entitlements, payments, *, observed_at):
    now = _time(observed_at)
    rights = {}
    for row in entitlements:
        key = row['event_id']
        require(isinstance(key, str) and key and key not in rights, 'DIVIDEND_DUPLICATE_ENTITLEMENT')
        require(row['kind'] == 'ORDINARY_CASH_DIVIDEND' and row['currency'] == 'USD', 'DIVIDEND_UNSUPPORTED_ACTION')
        require(type(row['eligible_shares']) is int and row['eligible_shares'] >= 0, 'DIVIDEND_SHARES')
        require(re.fullmatch('[a-f0-9]{64}', row['entitlement_evidence_sha256']) is not None, 'DIVIDEND_EVIDENCE')
        require(_time(row['available_at']) <= now and _time(row['entitlement_at']) <= now, 'DIVIDEND_NOT_AVAILABLE')
        require(_time(row['entitlement_at']) <= _time(row['payable_at']), 'DIVIDEND_DATES')
        amount = _amount(row['amount_per_share'])
        require(amount > 0, 'DIVIDEND_AMOUNT')
        rights[key] = dict(row=row, gross=amount * row['eligible_shares'])
    paid = {}
    seen = {}
    for payment in payments:
        identifier = payment['payment_id']
        require(type(identifier) is str and identifier, 'DIVIDEND_PAYMENT_ID')
        if identifier in seen:
            require(seen[identifier] == payment, 'DIVIDEND_PAYMENT_CONFLICT')
            continue
        seen[identifier] = payment
        key = payment['event_id']
        require(key in rights and key not in paid, 'DIVIDEND_PAYMENT_DUPLICATE_OR_UNKNOWN')
        require(re.fullmatch('[a-f0-9]{64}', payment['payment_evidence_sha256']) is not None, 'DIVIDEND_PAYMENT_EVIDENCE')
        right = rights[key]
        require(_time(right['row']['payable_at']) <= _time(payment['paid_at']) <= _time(payment['available_at']) <= now,
                'DIVIDEND_PAYMENT_TIME')
        require(payment['currency'] == 'USD' and payment['withholding'] is not None and payment['fees'] is not None,
                'DIVIDEND_DEDUCTIONS_REQUIRED')
        gross, tax, fee, net = (_amount(payment[field]) for field in ('gross', 'withholding', 'fees', 'net'))
        require(gross == right['gross'] and tax >= 0 and fee >= 0 and net >= 0 and gross-tax-fee == net,
                'DIVIDEND_PAYMENT_AMOUNTS')
        paid[key] = net
    return dict(status='RESEARCH_PROJECTION_NOT_POSTED',
        paid_cash=str(sum(paid.values(), Fraction(0))),
        unpaid_gross=str(sum((r['gross'] for key,r in rights.items() if key not in paid), Fraction(0))),
        paid_events=sorted(paid), account_mutated=False, entitlement_inferred=False,
        source_admission_performed=False)
