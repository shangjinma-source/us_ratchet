"""Materialize the sealed 20k candidate as a conditional paper plan, no search."""
import argparse
import hashlib
import json
from pathlib import Path

from data.current_quantity_portfolio_research import CurrentQuantityPortfolioResearch
from data.current_research_limit_plan import build_current_research_limit_plan


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = 'tmp/current_selected_three_price_unit_readback_20261014_v1.json'
CALENDAR = 'tmp/current_plan_calendar_web_observation_20261014_v1.json'
CONTRACT = 'research_contracts/current_snapshot_limit_plan_20261014_v1.json'


def materialize():
    def forbidden_search(**kwargs):
        raise AssertionError('This materializer may only read the sealed seed')

    research = CurrentQuantityPortfolioResearch(search=forbidden_search).calculate('20000')
    references = json.loads((ROOT / REFERENCE).read_text(encoding='utf-8-sig'))
    calendar = json.loads((ROOT / CALENDAR).read_text(encoding='utf-8-sig'))
    pins = dict(research['sources'])
    for path, expected in references['source_pins'].items():
        if path in pins and pins[path] != expected:
            raise ValueError('Conflicting source fingerprint')
        pins[path] = expected
    for path in (REFERENCE, CALENDAR, CONTRACT, 'data/current_research_limit_plan.py',
                 'tmp/current_selected_three_price_root_readback_20261014_v1.json',
                 'scripts/current_research_limit_plan_snapshot.py',
                 'research_contracts/user_broker_commission_confirmation_20261014.json'):
        pins[path] = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()

    def verify_sources():
        for path, expected in pins.items():
            if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != expected:
                raise ValueError(f'Source changed: {path}')

    verify_sources()
    by_ticker = {row['ticker']: row for row in references['rows']}
    quotes = []
    for stock in research['stocks']:
        row = by_ticker[stock['ticker']]
        if row['market_date'] != research['as_of'] or row['currency'] != 'USD':
            raise ValueError('Reference date/currency mismatch')
        quotes.append(dict(security_id=stock['security_id'], price=row['cent_display_reference'],
            as_of=row['market_date'], price_kind='PROVIDER_REGULAR_MARKET_PRICE_DECIMAL',
            price_basis='CURRENT_SHARE_USD_REFERENCE_CONDITIONAL', source_references=[REFERENCE]))
    arguments = dict(
        research_snapshot=dict(research_id=research['research_id'], as_of=research['as_of'],
            stocks=research['stocks'], source_hashes=pins),
        quotes=quotes, available_cash='20000', shares={},
        account_revision='ISOLATED_PAPER_INITIAL_20000_ZERO_SHARES_V1',
        decision_date=calendar['decision_date'], active_date=calendar['active_date'],
        calendar=[calendar['decision_date'], calendar['active_date']],
        strategy_version='FROZEN_TARGET_DIFFERENCE_PAPER_V1',
        target_quantities={row['security_id']: row['units'] for row in research['stocks']})
    plan = build_current_research_limit_plan(**arguments)
    if plan['status'] != 'READY' or not plan['execution_blocked']:
        raise ValueError(f'Invalid conditional plan: {plan.get("reason")}')
    verify_sources()
    return dict(status='CONDITIONAL_PAPER_SNAPSHOT_NOT_LIVE_ADVICE', arguments=arguments, plan=plan,
        market_session=calendar, search_calls=0, orders_submitted=0, account_changed=False,
        quote_note='Decimal provider regular-market reference; differs from flooring binary raw Close.',
        selection_note='Sealed candidate used for interface verification, not a newly approved strategy.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = materialize()
    destination = Path(args.output)
    with destination.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps(dict(status=result['status'], plan_id=result['plan']['plan_id'],
                         output=str(destination.resolve()))))


if __name__ == '__main__':
    main()
