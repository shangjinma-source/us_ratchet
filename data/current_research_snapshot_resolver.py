"""Resolve only known saved snapshots; never calculate or replace an unknown ID."""
from data.current_top1_portfolio_research import read_current_top1_research_snapshot
from data.current_quantity_portfolio_research import read_current_quantity_research_snapshot
from data.current_cash_portfolio_research import ResearchExpiredError


def read_known_research_snapshot(research_id):
    try:
        result = read_current_top1_research_snapshot(research_id)
    except ResearchExpiredError:
        result = read_current_quantity_research_snapshot(research_id)
    if result.get('research_id') != research_id:
        raise ValueError('SNAPSHOT_ID_MISMATCH')
    return result
