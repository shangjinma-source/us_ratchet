"""Read-only route, separate from legacy validation results."""
from fastapi import APIRouter
from data.verified_daily_comparison import read_verified_daily_comparison

router = APIRouter()


@router.get('/api/verified_daily_comparison')
def verified_daily_comparison():
    return read_verified_daily_comparison()
