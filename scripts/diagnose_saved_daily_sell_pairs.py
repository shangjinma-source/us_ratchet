"""Fixed saved SELL legs only; never run a strategy or fetch market data."""
import json
from pathlib import Path
from fractions import Fraction as F
from hashlib import sha256
from datetime import datetime, timezone


def sell_pair(history, active, quantity):
    if len(history)!=6 or type(quantity)is not int or quantity<=0:
        raise ValueError('SIX_BARS_AND_POSITIVE_INTEGER_QUANTITY_REQUIRED')
    def bar(value):
        result={k:F(value[k]) for k in ('open','high','low','close')}
        if not (0<result['low']<=min(result['open'],result['close'])<=max(result['open'],result['close'])<=result['high']):
            raise ValueError('INVALID_OHLC')
        return result
    bars=[bar(x) for x in history];today=bar(active)
    tr=[max(b['high']-b['low'],abs(b['high']-a['close']),abs(b['low']-a['close'])) for a,b in zip(bars,bars[1:])]
    median=sorted(tr)[2];unrounded=bars[-1]['close']+median/2
    cents=unrounded*100;limit=F(-(-cents.numerator//cents.denominator),100)
    price=today['open'] if today['open']>limit else (limit if today['high']>limit else None)
    baseline=quantity*today['open'];cash=quantity*price if price is not None else F(0)
    inventory=F(0) if price is not None else quantity*today['close']
    return dict(median_five_tr=str(median),limit=str(limit),baseline_price=str(today['open']),
        baseline_cash=str(baseline),premium_status='FILLED' if price is not None else 'EXPIRED_UNSOLD',
        premium_price=str(price) if price is not None else None,premium_cash=str(cash),
        unsold_quantity=0 if price is not None else quantity,unsold_mark=str(inventory),
        cash_shortfall_vs_baseline=str(baseline-cash),marked_opportunity_difference=str(cash+inventory-baseline),
        both_filled_proceeds_uplift=str(cash-baseline) if price is not None else None)


def run(root, output):
    spec_path=output/'spec.json';spec=json.loads(spec_path.read_bytes())
    if spec['schema']!='DAILY_SELL_LEG_DIAGNOSTIC_V1':raise ValueError('SPEC_REQUIRED')
    base=root/'tmp/daily_exclusion_B0_20261016_v1';prepared_path=root/'tmp/daily_verified_domain_experiment_20261016_v2/prepared.json'
    prepared=json.loads(prepared_path.read_bytes());outcome=json.loads((base/'outcome.json').read_bytes());pre=json.loads((base/'preflight.json').read_bytes())
    if sha256(prepared_path.read_bytes()).hexdigest()!=pre['prepared_sha256'] or json.loads((base/'terminal.json').read_bytes())['status']!='COMPLETE':raise ValueError('SAVED_SOURCE_BINDING')
    if outcome['fee_bps']!='0' or outcome['slippage_bps']!='0':raise ValueError('ZERO_COST_SPEC_MISMATCH')
    orders={o['id']:o for a in outcome['provider_audit'] for o in a['orders']};rows=[]
    for executed in outcome['order_log']:
        if executed.get('side')!='SELL':continue
        order=orders[executed['id']];sid=executed['security_id'];day=order['decision_date'];dates=prepared['session_dates'];i=dates.index(day);window=dates[max(0,i-5):i+1]
        if len(window)!=6 or dates[i+1]!=executed['date'] or order['active_date']!=executed['date'] or order['quantity']!=executed['quantity']:
            raise ValueError('ORDER_CAUSAL_WINDOW_MISMATCH')
        for kind in ('split_events_reference_only','distribution_events','supported_conversions','cash_stock_merger_events','identity_migrations'):
            for event in prepared[kind]:
                if sid in str(event) and any(d in str(event) for d in window+[executed['date']]):raise ValueError('ACTION_WINDOW_REQUIRES_EXPLICIT_NORMALIZATION')
        bars=prepared['ohlc'][sid];pair=sell_pair([bars[d] for d in window],bars[executed['date']],executed['quantity'])
        if F(pair['baseline_price'])!=F(executed['price']):raise ValueError('SAVED_BASELINE_PRICE_MISMATCH')
        rows.append(dict(order_id=executed['id'],security_id=sid,ticker=prepared['metadata'][sid]['ticker'],quantity=executed['quantity'],decision_date=day,execution_date=executed['date'],history_dates=window,source_provenance=prepared['source_provenance'].get(sid),**pair))
    def total(key):return str(sum((F(x[key]) for x in rows if x[key] is not None),F(0)))
    filled=[x for x in rows if x['premium_status']=='FILLED']
    inputs=[spec_path,prepared_path,base/'outcome.json',base/'preflight.json',base/'terminal.json',Path(__file__).resolve()]
    report=dict(schema='DAILY_SELL_LEG_DIAGNOSTIC_RESULT_V1',created_at=datetime.now(timezone.utc).isoformat(),status='COMPLETE_DESCRIPTIVE_ONLY',
        source_hashes={str(p.relative_to(root)):sha256(p.read_bytes()).hexdigest() for p in inputs},rows=rows,
        historical_price_basis='CONDITIONAL_RESTORED_HISTORICAL_NOMINAL_NOT_CERTIFIED',
        summary=dict(scope='Fixed twelve conditional daily SELL events, not full strategy or portfolio return',pair_count=len(rows),premium_filled=len(filled),premium_expired=len(rows)-len(filled),
            baseline_cash_sum=total('baseline_cash'),premium_cash_sum=total('premium_cash'),unsold_same_day_mark_sum=total('unsold_mark'),
            baseline_cash_not_realized_on_unsold_legs=str(sum((F(x['baseline_cash']) for x in rows if x['premium_status']!='FILLED'),F(0))),
            all_pair_marked_opportunity_difference=total('marked_opportunity_difference'),both_filled_proceeds_uplift=total('both_filled_proceeds_uplift')),
        assumptions=spec,portfolio_return=None,annualized_return=None,economic_winner=None,strategy_runs=0,network_calls=0,production_changed=False)
    with (output/'report.json').open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
    return report

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    print(json.dumps(run(root,root/'tmp/daily_sell_pair_20261016_v1')['summary']))
