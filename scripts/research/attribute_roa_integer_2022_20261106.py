"""Completed calendar-year attribution only; never annualize a partial run."""
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from backtest.research_exact_fraction_json import loads
from scripts.research.screen_profitability_daily_regime_20261106 import read_qqq

ROOT=Path(__file__).resolve().parents[2]


def main():
    path=ROOT/'tmp/roa_daily_account_20261106_v16/book.json'
    raw=path.read_bytes();book=loads(raw.decode())
    rows=book['daily_ledger']
    anchor=[r for r in rows if r['date']<'2022-01-01'][-1]
    year=[r for r in rows if r['date'].startswith('2022-')]
    assert anchor['date']=='2021-12-31' and year[-1]['date']=='2022-12-30'
    assert len(year)==251 and [r['date'] for r in year]==sorted({r['date'] for r in year})
    pins={};qqq=read_qqq(pins)
    assert [r['date'] for r in year]==sorted(d for d in qqq if d.startswith('2022-'))
    peak=Fraction(anchor['equity']);drawdown=Fraction(0)
    for row in year:
        equity=Fraction(row['equity']);peak=max(peak,equity)
        drawdown=max(drawdown,1-equity/peak)
    output=dict(scope='COMPLETED_2022_CALENDAR_YEAR_ONLY_NOT_FULL_PERIOD_ADMISSION',
        anchor_date=anchor['date'],last_date=year[-1]['date'],sessions=len(year),
        return_pct=float((Fraction(year[-1]['equity'])/Fraction(anchor['equity'])-1)*100),
        within_year_max_drawdown_pct=float(drawdown*100),end_cash_only=not bool(year[-1]['shares']),
        book_sha256=sha256(raw).hexdigest(),full_book_status=book['status'],
        calendar_check='EXACT_MATCH_EXISTING_QQQ_SESSION_DATES',calendar_source_hashes=pins,
        limitation='Year-local drawdown, not full-history maximum. Gross dividends and 5bp execution slippage; zero commission research assumption. Whole book still incomplete.')
    (ROOT/'tmp/roa_integer_2022_20261106.json').write_text(json.dumps(output,indent=2))
    print(json.dumps(output,indent=2))


if __name__=='__main__':main()
