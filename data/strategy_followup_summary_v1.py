"""Read-only grouped price observations; repeated advice is not a trade sample."""
from fractions import Fraction
from pathlib import Path
from core.strategy_account_ledger import require
from data.strategy_followup_result_store_v1 import read_observation


def summarize(rows):
    groups = {}
    seen = set()
    for row in rows:
        require(row['observation_id'] not in seen, 'FOLLOWUP_SUMMARY_DUPLICATE')
        seen.add(row['observation_id'])
        require(row['status'] == 'CONDITIONAL_PRICE_OBSERVATION' and
                row['actual_fill_inferred'] is False and row['performance_computed'] is False,
                'FOLLOWUP_SUMMARY_NOT_TRADES')
        require(row['side'] in ('BUY', 'SELL'), 'FOLLOWUP_SUMMARY_SIDE')
        reference = Fraction(row['reference_limit'])
        close = Fraction(row['closing_price'])
        require(reference > 0 and close > 0, 'FOLLOWUP_SUMMARY_PRICE')
        change = close / reference - 1
        require(change == Fraction(row['price_change_vs_reference']), 'FOLLOWUP_SUMMARY_CHANGE')
        key = (row['security_id'], row['ticker'], row['observation_session'], row['side'])
        group = groups.setdefault(key, dict(closing_price=close, references=[], changes=[], ids=[]))
        require(group['closing_price'] == close, 'FOLLOWUP_SUMMARY_CLOSE_CONFLICT')
        group['references'].append(reference)
        group['changes'].append(change)
        group['ids'].append(row['observation_id'])
    items = []
    for key, group in sorted(groups.items()):
        security_id, ticker, session, side = key
        items.append(dict(security_id=security_id, ticker=ticker, observation_session=session,
            side=side, advice_observations=len(group['ids']), closing_price=str(group['closing_price']),
            reference_limit_min=str(min(group['references'])), reference_limit_max=str(max(group['references'])),
            price_change_min=str(min(group['changes'])), price_change_max=str(max(group['changes'])),
            observation_ids=sorted(group['ids'])))
    return dict(schema='DAILY_FOLLOWUP_SUMMARY_V1', items=items, observations=len(seen),
        stock_sessions=len({(key[0], key[2]) for key in groups}),
        actual_fill_inferred=False, performance_computed=False,
        notice='按股票、观察日期和买卖方向合并；重复刷新不是独立交易。价格变化不代表成交收益。')


def read_summary(directory):
    directory = Path(directory)
    index = directory / 'index'
    require(not index.is_symlink(), 'FOLLOWUP_SUMMARY_INDEX_SYMLINK')
    paths = sorted(index.glob('*.json'))
    require(len(paths) <= 1000, 'FOLLOWUP_SUMMARY_LIMIT')
    # Each row is read through the archive verifier, including all copied sources.
    return summarize([read_observation(directory, path.stem) for path in paths])
