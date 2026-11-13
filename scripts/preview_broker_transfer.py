"""GET-only first-funding preview bound to a verified live ROA snapshot."""
import argparse
from datetime import datetime, timezone
from fractions import Fraction
import json
from pathlib import Path

from core.broker_transfer_plan import plan_usmart_funding, fit_integer_buys
from scripts.verify_roa_live_advice import capture


def build_preview(*, verification, snapshot, hsbc_cash, usmart_cash,
                  other_fee_reserve, transfer_fee_reserve,
                  hsbc_waiver_exhausted, hsbc_minimum_cash='1300',
                  broker_holdings=None):
    pending = dict(status='WAIT_VERIFIED_ADVICE', executable=False)
    if verification.get('api_advice_passed') is not True:
        return pending
    account = snapshot['account']
    positions = []
    # Explicit revision-bound ownership; transfers never create duplicate positions.
    if account['orders']:
        return dict(status='BROKER_HOLDINGS_MAPPING_REQUIRED', executable=False)
    if account['holdings']:
        if not isinstance(broker_holdings, dict):
            return dict(status='BROKER_HOLDINGS_MAPPING_REQUIRED', executable=False)
        if broker_holdings.get('account_revision') != account['revision']:
            return dict(status='BROKER_HOLDINGS_REVISION_MISMATCH', executable=False)
        totals = {}
        seen = set()
        positions = broker_holdings.get('positions')
        if not isinstance(positions, list):
            return dict(status='BROKER_HOLDINGS_INVALID', executable=False)
        for row in positions:
            if not isinstance(row, dict):
                return dict(status='BROKER_HOLDINGS_INVALID', executable=False)
            broker, security, quantity = row.get('broker'), row.get('security_id'), row.get('quantity')
            if (broker not in ('HSBC', 'USMART') or not isinstance(security, str)
                    or type(quantity) is not int or quantity <= 0
                    or (broker, security) in seen):
                return dict(status='BROKER_HOLDINGS_INVALID', executable=False)
            seen.add((broker, security))
            totals[security] = totals.get(security, 0) + quantity
        expected = {row['security_id']: row['quantity'] for row in account['holdings']}
        if totals != expected:
            return dict(status='BROKER_HOLDINGS_TOTAL_MISMATCH', executable=False)
    if Fraction(hsbc_cash) + Fraction(usmart_cash) != Fraction(account['available_cash']):
        return dict(status='BROKER_CASH_TOTAL_MISMATCH', executable=False)
    orders = snapshot['difference']['new_orders']
    tickers = {row['security_id']: row['ticker'] for row in snapshot['rows']}
    inventory = {(row['broker'], row['security_id']): row['quantity'] for row in positions}
    sells = []
    for order in orders:
        if order['side'] == 'BUY':
            continue
        if order['side'] != 'SELL' or type(order['quantity']) is not int or order['quantity'] <= 0:
            return dict(status='INVALID_BROKER_ORDER', executable=False)
        remaining = order['quantity']
        for broker in ('HSBC', 'USMART'):
            key = (broker, order['security_id'])
            quantity = min(remaining, inventory.get(key, 0))
            if quantity:
                sells.append(dict(broker=broker, symbol=tickers[order['security_id']],
                                  quantity=quantity, limit_price=order['limit_price']))
                inventory[key] -= quantity
                remaining -= quantity
        if remaining:
            return dict(status='BROKER_SELL_EXCEEDS_HOLDINGS', executable=False)
    buys = [dict(symbol=tickers[order['security_id']], quantity=order['quantity'],
                 limit_price=order['limit_price']) for order in orders if order['side'] == 'BUY']
    result = plan_usmart_funding(
        hsbc_cash=hsbc_cash, usmart_cash=usmart_cash, buys=buys,
        other_fee_reserve=other_fee_reserve,
        transfer_fee_reserve=transfer_fee_reserve,
        hsbc_waiver_exhausted=hsbc_waiver_exhausted,
        hsbc_minimum_cash=hsbc_minimum_cash)
    original_buys = buys
    if buys and Fraction(hsbc_cash) < Fraction(hsbc_minimum_cash) and Fraction(result['proposed_transfer_credit_usd']) > 0:
        return dict(status='HSBC_MINIMUM_RESERVE_NOT_MET', executable=False)
    if result['status'] == 'INSUFFICIENT_TOTAL_CASH':
        buys = fit_integer_buys(buys=buys,
            available_cash=Fraction(usmart_cash)+Fraction(result['maximum_transfer_credit_usd']),
            other_fee_reserve=other_fee_reserve)
        result = plan_usmart_funding(hsbc_cash=hsbc_cash, usmart_cash=usmart_cash,
            buys=buys, other_fee_reserve=other_fee_reserve,
            transfer_fee_reserve=transfer_fee_reserve,
            hsbc_waiver_exhausted=hsbc_waiver_exhausted, hsbc_minimum_cash=hsbc_minimum_cash)
    result.update(account_revision=account['revision'],
                  proposal_id=snapshot['proposal_id'], target_id=snapshot['target_id'],
                  quote_valid_until=snapshot['quote_valid_until'],
                  execution_session=snapshot['execution_session'],
                  planned_usmart_buys=buys, planned_hsbc_buys=[],
                  planned_broker_sells=sells, unfilled_sale_proceeds_included=False,
                  sell_fees_included=False,
                  original_strategy_buys=original_buys,
                  budget_reduced=buys != original_buys,
                  requires_reprice_after_transfer=True,
                  scope='INITIAL_FUNDING_PREVIEW_NOT_BROKER_ORDER_ROUTING')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hsbc-cash', required=True)
    parser.add_argument('--usmart-cash', required=True)
    parser.add_argument('--other-fee-reserve', required=True)
    parser.add_argument('--transfer-fee-reserve', required=True)
    parser.add_argument('--hsbc-waiver-exhausted', action='store_true')
    parser.add_argument('--base-url', default='http://127.0.0.1:8010')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    verification = capture(args.base_url, output)
    snapshot = json.loads((output/'snapshot.json').read_text(encoding='utf-8'))
    result = build_preview(verification=verification, snapshot=snapshot,
        hsbc_cash=args.hsbc_cash, usmart_cash=args.usmart_cash,
        other_fee_reserve=args.other_fee_reserve,
        transfer_fee_reserve=args.transfer_fee_reserve,
        hsbc_waiver_exhausted=args.hsbc_waiver_exhausted)
    result['generated_at'] = datetime.now(timezone.utc).isoformat()
    result['reserve_assumptions'] = dict(other_fee_usd=args.other_fee_reserve,
                                        transfer_fee_usd=args.transfer_fee_reserve)
    (output/'funding_preview.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
