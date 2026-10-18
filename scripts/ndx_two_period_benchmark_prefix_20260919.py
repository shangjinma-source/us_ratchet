"""Read and audit immutable 21-session incumbent/NAV prefixes; never replay engines."""
import argparse,csv,gzip,hashlib,io,json,sys
from copy import deepcopy
from datetime import datetime
from decimal import Decimal,localcontext
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_root_price_archive_contract_research as archive
from scripts.ndx_base_three_cell_window_delta_research import publish
BASE=ROOT/'data/cache/research'
BOUND={
 'calendar':('corrected_explicit_path_20260919_v1/calendar.json','57ac5d3187c656694a5351fda4cde7ce4331f9e471bcfc8881930c8b9984fa1c'),
 'control':('incumbent_price_source_probe_20260912_v1/nominal_control_20260912.json','53d2beb410c37393df266dd6709621dec27822b1b50db5d0623415b2d4ad8ac1'),
 'oracle':('incumbent_price_source_probe_20260912_v1/nominal_control_accounting_oracle_20260912.json','d9615b4fe0405ce71b0902045c25c8a482431e1bc4f8c4fd1a9654d7c51c5bee'),
 'nav':('dynamic_frozen_v2/preference_retrospective_nav_20260912.json','e1bb2b71d777b39cea5526ce4cc39a7b90d281609d3d2b9d8d0a0dbaa8a28b33'),
 'basis':('incumbent_price_source_probe_20260912_v1/incumbent_price_basis_review_20260912.json','6565e1cc5233f148d683d134ca95a29886530f8ab25cf48e3c839aa21864293f'),
 'old':('dynamic_frozen_v2/strict_return_control_20260911.json','87b081061374a368c0c7d1b6a3d953ba964c3ac2e30d56f3a7173e21d1c3b58b')}
CLOCK=[('2023-03-31','2023-04-03'),('2023-04-28','2023-05-01')]
END='2023-05-01';START='2023-03-31';NY=ZoneInfo('America/New_York')
LOADED={str(p):archive.drift.file_sha(p) for p in (Path(__file__).resolve(),archive.SOURCE,Path(publish.__code__.co_filename).resolve())}
FALSE=('execution_rerun','fit_performed','risk_projection_recomputed','candidate_eligibility_claimed','risk_is_order_gate','cash_dividends_modelled','nav_publication_time_verified','currency_fx_equivalence_verified','subscription_redemption_fee_equivalence_verified','provider_identity_verified','complete_actions_verified','historical_full_source_closure_verified','point_in_time_verified','promotion_allowed','comparison_winner_selected')


def unique(pairs):
    out={}
    for k,v in pairs:
        if k in out:raise ValueError('Duplicate JSON key')
        out[k]=v
    return out


def number(v):
    if type(v) not in (int,float,Decimal):raise ValueError('Nonboolean finite number required')
    d=Decimal(str(v))
    if not d.is_finite():raise ValueError('Finite value required')
    return d


def check(actual,expected):
    error=abs(number(actual)-expected)
    if error>Decimal('1e-8'):raise ValueError('Independent Decimal account mismatch')
    return error


def exact(a,b):return json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False)


def metrics(values):
    if len(values)!=21 or any(number(v)<=0 for v in values):raise ValueError('21 positive observed equity values required')
    values=[number(v) for v in values]
    with localcontext() as ctx:
        ctx.prec=50;ratio=values[-1]/values[0];peak=values[0];dd=Decimal(0)
        for value in values:peak=max(peak,value);dd=max(dd,1-value/peak)
        return dict(path_return=str(ratio-1),annualized_return_252_over_20=str(ratio**(Decimal(252)/20)-1),path_max_drawdown=str(dd),observation_count=21,return_interval_count=20,annualization_is_short_window_diagnostic=True)


def nominal_from_raw(raw,ticker,calendar):
    decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
    data=json.loads(decoded,object_pairs_hook=unique,parse_float=Decimal)['chart']['result'][0]
    if data['meta']['symbol']!=ticker or data['meta']['currency']!='USD':raise ValueError('Raw channel coordinate differs')
    times=data['timestamp']
    if any(type(t) is not int for t in times):raise ValueError('Integer raw timestamps required')
    dates=[datetime.fromtimestamp(t,NY).date().isoformat() for t in times]
    if dates!=sorted(set(dates)) or [d for d in dates if START<=d<=END]!=calendar:raise ValueError('Complete original raw prefix calendar required')
    quote,=data['indicators']['quote']
    if any(len(quote[k])!=len(times) for k in ('open','close')):raise ValueError('Raw quote dimensions differ')
    events=[]
    for key,e in data.get('events',{}).get('splits',{}).items():
        if type(e['date']) is not int or str(e['date'])!=key:raise ValueError('Split timestamp/key differs')
        day=datetime.fromtimestamp(e['date'],NY).date().isoformat();n=number(e['numerator']);d=number(e['denominator'])
        if n<=0 or d<=0 or START<=day<=END:raise ValueError('No in-window action or invalid ratio permitted')
        events.append((day,n/d))
    out={}
    for day in calendar:
        factor=Decimal(1)
        for event,ratio in events:
            if event>day:factor*=ratio
        i=dates.index(day);out[day]={k:number(quote[k][i])*factor for k in ('open','close')}
        if any(v<=0 for v in out[day].values()):raise ValueError('Positive nominal O/C required')
    return out


def audit_control(control,old,calendar,prices):
    if len(calendar)!=21 or calendar!=sorted(set(calendar)) or calendar[0]!=START or calendar[-1]!=END:raise ValueError('Bound 21-session interval required')
    fixed=control['original_fixed_schedule'];execution=control['execution'];targets=old['execution']['decisions'][0]['targets']
    if not exact(fixed['original_weights'],old['original_weights']) or len(targets)!=8 or not exact({v['ticker']:v['target_weight'] for v in targets.values()},old['original_weights']):raise ValueError('Original eight target vector differs')
    if any(number(fixed[k])!=v for k,v in dict(initial_cash_usd=25000,minimum_cash_buffer_usd=100,transaction_cost_bps=10).items()):raise ValueError('Original execution capital/fee contract differs')
    if execution['risk_is_order_gate'] is not False or execution['original_target_weights_modified'] is not False or execution['corporate_actions']!=[] or execution['identity_events']!=[]:raise ValueError('Original control semantics differ')
    daily=[r for r in execution['daily'] if r['session']<=END];decisions=[r for r in execution['decisions'] if r['decision_date']<=END];fills=[r for r in execution['executions'] if r['session']<=END];trades=[r for r in execution['trades'] if r['session']<=END];schedule=[r for r in fixed['schedule'] if r['decision_date']<=END]
    if [r['session'] for r in daily]!=calendar or [(r['decision_date'],r['execution_date']) for r in decisions]!=CLOCK or [(r['decision_date'],r['execution_date']) for r in schedule]!=CLOCK or [(r['decision_date'],r['session']) for r in fills]!=CLOCK or len(trades)!=13:raise ValueError('Full prefix decision/fill/trade denominator differs')
    if not all(exact(r['targets'],targets) for r in decisions+schedule):raise ValueError('Fixed targets changed')
    cash=Decimal(25000);shares={};maximum=Decimal(0);fees=Decimal(0)
    def ck(a,e):
        nonlocal maximum
        maximum=max(maximum,check(a,e))
    for row in daily:
        date=row['session'];today=[t for t in trades if t['session']==date];fill=[f for f in fills if f['session']==date]
        if len(fill)>1 or (today and not fill):raise ValueError('Trade outside unique execution')
        if fill:
            f=fill[0];decision=next(d for d in decisions if d['decision_date']==f['decision_date'])
            if f['status']!='FILLED' or f['failure_reasons'] or not exact(f['shares_before'],shares) or not exact(f['desired_shares'],decision['desired_shares']) or not exact(f['frozen_delta'],decision['delta']):raise ValueError('Frozen order or holdings changed')
            ck(f['cash_before_usd'],cash)
            if set(f['prices'])!=set(targets):raise ValueError('Complete execution price vector required')
            for sid in targets:ck(f['prices'][sid],prices[targets[sid]['ticker']][date]['open'])
            wanted=decision['desired_shares']
            if any(type(v) is not int or v<0 for v in wanted.values()):raise ValueError('Whole nonnegative target shares required')
            delta={s:wanted.get(s,0)-shares.get(s,0) for s in set(wanted)|set(shares)}
            if any(type(v) is not int for v in decision['delta'].values()) or not exact(decision['delta'],delta):raise ValueError('Frozen delta must equal actual desired-minus-before whole shares')
            if {t['security_id'] for t in today}!={s for s,v in delta.items() if v} or len({t['security_id'] for t in today})!=len(today):raise ValueError('Complete nonzero trade set differs')
            fill_fees=Decimal(0)
            for t in today:
                sid=t['security_id'];ticker=targets[sid]['ticker'];price=prices[ticker][date]['open']
                if t['ticker']!=ticker or type(t['share_delta']) is not int or t['share_delta']!=delta[sid]:raise ValueError('Trade identity/delta differs')
                fee=abs(delta[sid]*price)*Decimal('.001');ck(t['price_usd'],price);ck(t['transaction_cost_usd'],fee);cash-=delta[sid]*price+fee;fees+=fee;fill_fees+=fee
            shares={s:v for s,v in wanted.items() if v};ck(f['cash_after_usd'],cash)
            ck(f['projected_cash_usd'],cash);ck(f['projected_fees_usd'],fill_fees)
            if cash<100 or not exact(f['shares_after'],shares):raise ValueError('Filled buffer or holdings differ')
        if not exact(row['shares'],shares) or set(row['prices'])!=set(shares) or set(row['tickers'])!=set(shares):raise ValueError('Daily whole-share continuity or mark denominator differs')
        ck(row['cash_usd'],cash)
        for sid,n in shares.items():
            if row['tickers'][sid]!=targets[sid]['ticker']:raise ValueError('Daily label differs')
            ck(row['prices'][sid],prices[targets[sid]['ticker']][date]['close'])
        ck(row['total_value_usd'],cash+sum(n*prices[targets[s]['ticker']][date]['close'] for s,n in shares.items()))
        for decision in [d for d in decisions if d['decision_date']==date]:
            if not exact(decision['shares_before'],shares) or decision['status']!='FROZEN':raise ValueError('Decision Close holdings differ')
            ck(decision['cash_before_usd'],cash)
            wanted=decision['desired_shares'];union=set(wanted)|set(shares)|set(targets)
            if set(wanted)!=set(targets) or any(type(v) is not int or v<0 for v in wanted.values()) or set(decision['prices'])!=union:raise ValueError('Complete decision target/Close price vector required')
            delta={s:wanted.get(s,0)-shares.get(s,0) for s in set(wanted)|set(shares)}
            if any(type(v) is not int for v in decision['delta'].values()) or not exact(decision['delta'],delta):raise ValueError('Decision delta must equal desired-minus-before whole shares')
            projected=cash;projected_fees=Decimal(0)
            for sid in union:
                price=prices[targets[sid]['ticker']][date]['close'];ck(decision['prices'][sid],price)
                change=delta.get(sid,0);fee=abs(change*price)*Decimal('.001');projected-=change*price+fee;projected_fees+=fee
            ck(decision['projected_cash_usd'],projected);ck(decision['projected_fees_usd'],projected_fees)
            if projected<100:raise ValueError('Decision projected cash buffer differs')
    return dict(schedule=deepcopy(schedule),decisions=deepcopy(decisions),executions=deepcopy(fills),trades=deepcopy(trades),daily=deepcopy(daily),original_weights=deepcopy(fixed['original_weights']),initial_cash_usd=25000,minimum_cash_buffer_usd=100,transaction_cost_bps=10,decimal_max_error=str(maximum),decimal_total_fees_usd=str(fees),metrics=metrics([r['total_value_usd'] for r in daily]))


def audit_nav(report,csv_bytes,calendar):
    nav=report['nav'];rows=[r for r in nav['rows'] if r['session']<=END]
    if [r['session'] for r in rows]!=calendar or nav['publication_time_verified'] is not False or nav['fx_modelled'] is not False or nav['subscription_redemption_fees_modelled'] is not False:raise ValueError('Original conditional NAV clock/scope differs')
    records=list(csv.DictReader(io.StringIO(csv_bytes.decode('utf-8-sig'))));dates=[r['Date'] for r in records]
    if dates!=sorted(set(dates)):raise ValueError('Unique snapshot NAV dates required')
    mapping={r['Date']:Decimal(r['Close']) for r in records};maximum=Decimal(0)
    for row in rows:
        date=max(d for d in dates if d<=row['session']);value=mapping[date]
        if date!=row['nav_date'] or value<=0:raise ValueError('Backward NAV date differs')
        maximum=max(maximum,check(row['nav'],value),check(row['equity_index'],value/number(rows[0]['nav'])))
    return dict(role='012922_NATIVE_CURRENCY_RETROSPECTIVE_NAV',rows=deepcopy(rows),decimal_max_error=str(maximum),metrics=metrics([r['equity_index'] for r in rows]))


def build():
    sources=dict(LOADED)
    def read(path,sha,decode=True):
        path=Path(path).resolve();raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Bound artifact bytes differ')
        archive.merge(sources,{str(path):sha});return json.loads(raw,object_pairs_hook=unique) if decode else raw
    docs={k:read(BASE/p,h) for k,(p,h) in BOUND.items()}
    for doc in docs.values():
        for key in ('source_hashes','historical_expected_source_hashes'):
            if key in doc:archive.merge(sources,doc[key])
    calendar=[d for d in docs['calendar']['calendar'] if START<=d<=END]
    if docs['oracle']['engine_reexecuted'] is not False or docs['oracle']['daily_cash_shares_equity_rows_verified']!=295:raise ValueError('Original independent full accounting audit required')
    prices={}
    for row in docs['basis']['rows']:
        raw=read(row['price_response_path'],row['price_response_sha256'],False)
        prices[row['ticker']]=nominal_from_raw(raw,row['ticker'],calendar)
    navpaths=[p for p in docs['nav']['source_hashes'] if p.endswith('012922.csv')]
    if len(navpaths)!=1:raise ValueError('Unique immutable NAV source required')
    navraw=read(navpaths[0],docs['nav']['source_hashes'][navpaths[0]],False)
    contract=archive.load_contract();archive.verify_expected_sources(sources,contract)
    control=audit_control(docs['control'],docs['old'],calendar,prices);nav=audit_nav(docs['nav'],navraw,calendar)
    value=dict(schema='TWO_PERIOD_BENCHMARK_PREFIX_INDEPENDENT_ACCOUNTING_V1',calendar=calendar,decision_clock=CLOCK,incumbent=control,nav=nav,source_mode='SEALED_LONG_ACCOUNT_PREFIX_NOT_REEXECUTED',historical_expected_source_hashes=sources,archive_resolution=archive.verify_expected_sources(sources,contract),**dict.fromkeys(FALSE,False))
    verify(value);return value


def verify(value):
    required=dict(LOADED,**{str(BASE/p):h for p,h in BOUND.values()})
    if value['schema']!='TWO_PERIOD_BENCHMARK_PREFIX_INDEPENDENT_ACCOUNTING_V1' or any(value[k] is not False for k in FALSE):raise ValueError('Prefix scope differs')
    if any(value['historical_expected_source_hashes'].get(p)!=h for p,h in required.items()):raise ValueError('Required source omitted')
    if archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract())!=value['archive_resolution']:raise ValueError('Source partition differs')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args();value=build();verify(value);saved=publish(args.output,value);verify(value);print(json.dumps(saved))
