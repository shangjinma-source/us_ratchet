"""Partial, non-reinvested gross income overlay; never a spendable account ledger."""
from datetime import date
from fractions import Fraction


def build_schedule(events, observation_dates):
    dates = [date.fromisoformat(day) for day in observation_dates]
    if not dates or dates != sorted(set(dates)):
        raise ValueError('UNIQUE_ORDERED_OBSERVATION_DATES_REQUIRED')
    accounts = sorted({event['account'] for event in events})
    included, excluded, seen = [], [], set()
    for event in events:
        key = (event['account'], event['sid'], event['date'], event['kind'])
        if key in seen:
            raise ValueError('DUPLICATE_ENTITLEMENT')
        seen.add(key)
        if event.get('ready_for_conditional_gross_receivable_schedule') is not True:
            excluded.append(dict(account=key[0], security_id=key[1], ex_date=key[2],
                                 missing_fields=list(event.get('missing_fields', []))))
            continue
        terms = event['published_terms']
        ex_day, pay_day = date.fromisoformat(event['date']), date.fromisoformat(terms['payment_date'])
        quantity = event['quantity']
        if (event['kind'] != 'dividends' or type(quantity) is not int or quantity <= 0
                or terms['currency'] != 'USD' or not terms['share_unit']
                or terms['evidence_level'] != 'ISSUER_OR_SEC_WEB_OBSERVATION'
                or not dates[0] <= ex_day <= dates[-1] or pay_day < ex_day):
            raise ValueError('UNSUPPORTED_GROSS_ENTITLEMENT')
        rate = Fraction(terms['amount'])
        amount = rate * quantity
        if rate <= 0 or amount != Fraction(event['published_rate_times_quantity_exact']):
            raise ValueError('ENTITLEMENT_AMOUNT_MISMATCH')
        included.append(dict(account=key[0], security_id=key[1], ex_date=ex_day.isoformat(),
                             payment_date=pay_day.isoformat(), amount_exact=str(amount),
                             source_url=terms['url']))
    rows = []
    for day in dates:
        for account in accounts:
            accrued = sum((Fraction(e['amount_exact']) for e in included
                           if e['account'] == account and e['ex_date'] <= day.isoformat()), Fraction())
            paid = sum((Fraction(e['amount_exact']) for e in included
                        if e['account'] == account and e['payment_date'] <= day.isoformat()), Fraction())
            rows.append(dict(date=day.isoformat(), account=account,
                             theoretical_gross_paid_exact=str(paid),
                             outstanding_gross_receivable_exact=str(accrued - paid),
                             recognized_gross_income_exact=str(accrued)))
    return dict(status='PARTIAL_CONDITIONAL_GROSS_INCOME_ONLY', included=included,
                excluded=excluded, rows=rows, source_coverage_complete=False,
                account_cash_written=False, actual_payment_posting_verified=False,
                reinvestment_modeled=False, complete_total_return=None,
                note='Issuer payment dates model theoretical gross payment only; no tax, fees, rounding or actual broker posting assumed.')
