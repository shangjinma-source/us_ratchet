"""GET-only first-funding preview bound to a verified live ROA snapshot."""
import argparse
from datetime import datetime, timezone
from fractions import Fraction
import json
from pathlib import Path

from core.broker_transfer_plan import plan_usmart_funding
from scripts.verify_roa_live_advice import capture


def build_preview(*, verification, snapshot, hsbc_cash, usmart_cash,
                  other_fee_reserve, transfer_fee_reserve,
                  hsbc_waiver_exhausted, hsbc_minimum_cash='1300'):
    pending = dict(status='WAIT_VERIFIED_ADVICE', executable=False)
    if verification.get('api_advice_passed') is not True:
        return pending
    account = snapshot['account']
    # First migration only. Never infer where an existing holding/order lives.
    if account['holdings'] or account['orders']:
        return dict(status='BROKER_HOLDINGS_MAPPING_REQUIRED', executable=False)
    if Fraction(hsbc_cash) + Fraction(usmart_cash) != Fraction(account['available_cash']):
        return dict(status='BROKER_CASH_TOTAL_MISMATCH', executable=False)
    orders = snapshot['difference']['new_orders']
    if any(order['side'] != 'BUY' for order in orders):
        return dict(status='BROKER_HOLDINGS_MAPPING_REQUIRED', executable=False)
    tickers = {row['security_id']: row['ticker'] for row in snapshot['rows']}
    buys = [dict(symbol=tickers[order['security_id']], quantity=order['quantity'],
                 limit_price=order['limit_price']) for order in orders]
    result = plan_usmart_funding(
        hsbc_cash=hsbc_cash, usmart_cash=usmart_cash, buys=buys,
        other_fee_reserve=other_fee_reserve,
        transfer_fee_reserve=transfer_fee_reserve,
        hsbc_waiver_exhausted=hsbc_waiver_exhausted,
        hsbc_minimum_cash=hsbc_minimum_cash)
    result.update(account_revision=account['revision'],
                  proposal_id=snapshot['proposal_id'], target_id=snapshot['target_id'],
                  quote_valid_until=snapshot['quote_valid_until'],
                  execution_session=snapshot['execution_session'],
                  planned_usmart_buys=buys, planned_hsbc_buys=[],
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
