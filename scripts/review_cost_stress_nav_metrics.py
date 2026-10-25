"""Saved-state NAV composition and independent metrics; no strategy execution."""
from datetime import date
from fractions import Fraction as F
import math
from backtest.return_priority_cash_stock_entitlements import value_cash_stock_entitlements
from backtest.return_priority_distribution_entitlements import value_distributions


def review(*, outcome, metrics, assembled, ohlc, initial_cash='20000'):
    def require(ok, reason):
        if not ok: raise ValueError(reason)
    require(outcome['status']=='COMPLETE', 'COMPLETE_OUTCOME_REQUIRED')
    sessions=assembled['session_dates']; rows=outcome['daily_ledger']
    require([r['date'] for r in rows]==sessions[1:], 'SESSION_COVERAGE_MISMATCH')
    current=peak=F(initial_cash); worst=F(0); years={}; rights_days=0
    for row in rows:
        day=row['date']; cash=F(row['cash']); shares=row['shares']
        require(cash>=0 and all(type(q) is int and q>=0 for q in shares.values()), 'INVALID_REPORTED_STATE')
        stock=sum((q*F(ohlc[sid][day]['close']) for sid,q in shares.items() if q), F(0))
        require(stock==F(row['stock_value']), 'STOCK_VALUATION_MISMATCH')
        require(F(row['external_flow'])==0, 'EXTERNAL_FLOW_UNSUPPORTED')
        marks={sid:dict(date=day,price=str(ohlc[sid][day]['close']),
                       source_references=assembled['price_source_references'].get(sid,[]))
               for sid in ohlc if day in ohlc[sid]}
        pending=distribution=F(0)
        if row['merger_entitlements']:
            valued=value_cash_stock_entitlements(state=dict(cash=str(cash), shares=shares,
                merger_entitlements=row['merger_entitlements']), marks=marks, as_of=day,
                fractional_settlements=assembled['fractional_settlements'])
            require(valued['status']!='BLOCKED', 'MERGER_REVALUATION_BLOCKED')
            pending=F(valued['total_equity'])-cash-stock
        if row['distribution_rights']:
            valued=value_distributions(state=dict(cash=str(cash), shares=shares,
                distribution_rights=row['distribution_rights']),marks=marks,as_of=day,
                fractional_cash_values=assembled['distribution_fractional_cash_values'])
            require(valued['status']!='BLOCKED', 'DISTRIBUTION_REVALUATION_BLOCKED')
            distribution=F(valued['total_equity'])-cash-stock
        require(pending==F(row['nontradable_entitlement_value']) and
                distribution==F(row['distribution_entitlement_value']), 'RIGHTS_VALUATION_MISMATCH')
        rights_days += bool(row['merger_entitlements'] or row['distribution_rights'])
        year=date.fromisoformat(day).year
        if year not in years: years[year]=dict(opening=current,peak=current,drawdown=F(0),sessions=0)
        current=cash+stock+F(row['receivable'])+pending+distribution
        require(current>0 and current==F(row['equity']), 'NAV_COMPOSITION_MISMATCH')
        peak=max(peak,current);worst=max(worst,1-current/peak)
        annual=years[year];annual['peak']=max(annual['peak'],current)
        annual['drawdown']=max(annual['drawdown'],1-current/annual['peak'])
        annual.update(closing=current,through=day,sessions=annual['sessions']+1)
    require(current==F(metrics['final_equity']) and worst==F(metrics['maximum_close_drawdown']), 'WHOLE_METRICS_MISMATCH')
    ratio=current/F(initial_cash)
    require(ratio-1==F(metrics['total_return']), 'TOTAL_RETURN_MISMATCH')
    elapsed=(date.fromisoformat(sessions[-1])-date.fromisoformat(sessions[0])).days
    require(elapsed>0,'NONPOSITIVE_ELAPSED_DAYS')
    cagr=float(ratio)**(365/elapsed)-1
    require(math.isclose(cagr,metrics['cagr'],rel_tol=1e-12,abs_tol=1e-12),'CAGR_MISMATCH')
    require(F(metrics['cagr_exact_inputs']['wealth_ratio'])==ratio and
            F(metrics['cagr_exact_inputs']['exponent'])==F(365,elapsed),'CAGR_INPUT_MISMATCH')
    require([y['year'] for y in metrics['years']]==sorted(years),'YEAR_COVERAGE_MISMATCH')
    for y in metrics['years']:
        computed=years[y['year']]
        require(F(y['return_fraction'])==computed['closing']/computed['opening']-1
                and F(y['maximum_close_drawdown'])==computed['drawdown']
                and y['sessions']==computed['sessions'] and y['through']==computed['through'], 'ANNUAL_METRICS_MISMATCH')
    return dict(status='SAVED_STATE_NAV_AND_METRICS_VERIFIED',sessions=len(rows),
        final_equity=str(current),maximum_close_drawdown=str(worst),cagr=cagr,rights_valuation_days=rights_days,
        holdings_independently_replayed=False,source_prices_authenticated=False,
        limitations=['Metrics calculated independently from reconstructed saved-state NAV.',
          'Corporate rights valuation reuses production arithmetic; rights eligibility, ownership, delivery, receivables and holdings are supplied saved states, not independently reconstructed.',
          'Does not establish historical data accuracy, full portfolio replay, selection validity or independent OOS performance.'])
