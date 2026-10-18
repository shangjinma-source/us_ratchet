"""Fixed-fill gross income memorandum; never changes trading cash or reruns a book."""
import hashlib
import json
from datetime import date
from fractions import Fraction
from pathlib import Path


def project(events, account_dates):
    seen = set()
    for event in events:
        key = (event['account'], event['security_id'], event['ex_date'])
        if key in seen:
            raise ValueError('DUPLICATE_ENTITLEMENT')
        seen.add(key)
        if event['account'] not in account_dates:
            raise ValueError('UNKNOWN_ACCOUNT')
        if date.fromisoformat(event['payment_date']) < date.fromisoformat(event['ex_date']):
            raise ValueError('PAYMENT_BEFORE_EX_DATE')
        if event['aggregation_currency'] not in ('USD', 'EUR') or Fraction(event['aggregation_amount_exact']) <= 0:
            raise ValueError('INVALID_CURRENCY_OR_AMOUNT')
    timeline = []
    terminal = {}
    for account, dates in account_dates.items():
        if not dates or dates != sorted(set(dates)):
            raise ValueError('INVALID_CALENDAR')
        for day in dates:
            date.fromisoformat(day)
            legs = {}
            for currency in ('USD', 'EUR'):
                eligible = [e for e in events if e['account'] == account and e['aggregation_currency'] == currency and e['ex_date'] <= day]
                accrued = sum((Fraction(e['aggregation_amount_exact']) for e in eligible), Fraction())
                paid = sum((Fraction(e['aggregation_amount_exact']) for e in eligible if e['payment_date'] <= day), Fraction())
                legs[currency] = {'gross_accrued_exact': str(accrued), 'theoretical_gross_paid_exact': str(paid), 'gross_receivable_exact': str(accrued-paid)}
            row = {'account': account, 'date': day, 'legs': legs}
            timeline.append(row)
        terminal[account] = {'date': dates[-1], 'legs': legs, 'outstanding': [e for e in events if e['account'] == account and e['ex_date'] <= dates[-1] < e['payment_date']]}
    return {'timeline': timeline, 'terminal': terminal}


def prepare(root):
    root = Path(root)
    pins = {}
    def read(path):
        raw = (root/path).read_bytes()
        pins[path] = hashlib.sha256(raw).hexdigest()
        value = json.loads(raw)
        for source, digest in value.get('source_hashes', {}).items():
            if hashlib.sha256((root/source).read_bytes()).hexdigest() != digest:
                raise ValueError('SOURCE_HASH_MISMATCH:'+source)
            if source in pins and pins[source] != digest:
                raise ValueError('SOURCE_PIN_CONFLICT')
            pins[source] = digest
        return value
    us = read('tmp/actual_exposed_us_dividend_supplement_20261015_v1/supplement.json')
    foreign = read('tmp/actual_exposed_foreign_dividend_supplement_20261015_v1/supplement.json')
    base = read('tmp/actual_exposed_entitlements_20261015_v1.json')
    events = []
    for event in us['merged_gross_schedule']:
        events.append({**event, 'aggregation_currency': 'USD', 'aggregation_amount_exact': event['gross_entitlement_usd_exact'], 'original_currency': 'USD', 'original_amount_exact': event['gross_entitlement_usd_exact']})
    for event in foreign['events']:
        converted = event['ticker'] == 'ASML' and event.get('usd_gross_entitlement_exact') is not None
        events.append({'account': event['account'], 'ticker': event['ticker'], 'security_id': event['security_id'], 'ex_date': event['ex_date'], 'payment_date': event['payment_date'], 'opening_quantity': event['opening_quantity'], 'aggregation_currency': 'USD' if converted else event['currency'], 'aggregation_amount_exact': event['usd_gross_entitlement_exact'] if converted else event['gross_entitlement_exact'], 'original_currency': event['currency'], 'original_amount_exact': event['gross_entitlement_exact'], 'original_amount_is_nonadditive_disclosure': converted, 'usd_fixing_exact': event.get('usd_conversion_rate_exact'), 'terms_source': 'FOREIGN_SUPPLEMENT'})
    assert len(events) == 31
    original = {(r['account'], r['sid'], r['date']): r['quantity'] for r in base['events']}
    assert {(r['account'], r['security_id'], r['ex_date']): r['opening_quantity'] for r in events} == original
    paths = {'original8': 'tmp/original_weight_next12_actual_20261015_v1/book/outcome.json', 'quantity': 'tmp/next12_monthly_comparison_20261015_v1/quantity/outcome.json', 'top1': 'tmp/next12_top1_pin_repair_20261015_v1/top1/outcome.json'}
    calendars = {}
    for account, path in paths.items():
        outcome = read(path)
        calendars[account] = ['2025-07-31']+[r['date'] for r in outcome['daily_ledger']]
        assert len(calendars[account]) == 251 and calendars[account][-1] == '2026-07-30'
    assert len({tuple(d) for d in calendars.values()}) == 1
    output = project(events, calendars)
    assert len(output['timeline']) == 753
    # Single additive July leg: original EUR is disclosure, never a second entitlement.
    terminal = output['terminal']['original8']['legs']
    assert terminal['EUR']['gross_accrued_exact'] == '59/10'
    assert Fraction(terminal['USD']['gross_receivable_exact']) == Fraction('2.137748')
    assert terminal['EUR']['gross_receivable_exact'] == '0'
    script = Path(__file__).resolve().relative_to(root.resolve()).as_posix()
    pins[script] = hashlib.sha256((root/script).read_bytes()).hexdigest()
    output.update(schema='FIXED_FILL_GROSS_MULTICURRENCY_INCOME_TIMELINE_V1', status='COMPLETE_FOR_31_KNOWN_EXPOSED_EVENTS_ONLY', events=events, source_hashes=pins, row_count=753, event_count=31, book_calls=0, economic_search_calls=0, account_writes=0, net_amount_certified=False, complete_total_return=False, policy={'reinvestment':False,'personal_tax_deducted':False,'fee_deducted':False,'rounding':'EXACT_RATIONAL_NO_CENT_ROUNDING','payment':'THEORETICAL_GROSS_SCHEDULE_NOT_BROKER_POSTING','EUR_paid_leg':'UNCONVERTED_ORIGINAL_CURRENCY_MEMORANDUM_NOT_ACTUAL_NYRS_EUR_CASH','USD_EUR_aggregation':'NEVER_SUM_DIFFERENT_CURRENCIES','July_ASML':'USD_ADDITIVE_EUR_DISCLOSURE_ONLY; PAY2026-08-05_OUTSIDE_PERIOD'}, limitations=['Only the31 known exposure events are covered; event universe completeness is not certified.','No sealed cash/shares/orders/equity/CAGR/DD changed.','Original-currency memorandum and known USD fixation are data projections, not executable cash or verified net settlement.'])
    return output


if __name__ == '__main__':
    result = prepare(Path(__file__).resolve().parents[1])
    path = Path('tmp/actual31_gross_multicurrency_timeline_20261015_v1.json')
    with path.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'terminal':result['terminal']}))
