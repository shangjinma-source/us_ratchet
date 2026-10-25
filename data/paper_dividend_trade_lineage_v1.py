"""Read-only prerequisite for joining dividend and trade histories.

This does not credit trading cash or authorize a descriptor migration.
"""
from backtest.current_strategy_prospective_paper_book_v1 import replay as replay_book
from backtest.paper_dividend_journal_v1 import replay as replay_dividends, digest
from core.strategy_account_ledger import require


def reconcile(book, journal, *, evidence):
    replay_book(book, authority=evidence['authority'],
                admitted_decisions=evidence['admitted_decisions'],
                admitted_settlements=evidence['admitted_settlements'])
    replay_dividends(journal, **evidence)
    require(all(book[key] == value for key, value in journal['identity'].items()),
            'DIVIDEND_TRADE_IDENTITY_MISMATCH')
    initial = digest(dict(registration=book['registration_sha256'],
                          initialized_at=book['initialized_at']))
    ancestors = {initial, *(operation['revision'] for operation in book['operations'])}
    for entry in journal['entries']:
        require(entry['request']['book_revision'] in ancestors,
                'DIVIDEND_TRADE_NONANCESTOR_BOOK')
    return dict(schema='PAPER_DIVIDEND_TRADE_LINEAGE_REVIEW_V1',
                status='SAME_TRADE_LINEAGE_VERIFIED_NOT_CASH_INTEGRATED',
                trade_revision=book['revision'], dividend_revision=journal['revision'],
                reviewed_payments=len(journal['entries']),
                spendable_cash_integrated=False, account_writes=False)
