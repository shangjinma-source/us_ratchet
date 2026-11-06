"""GET-only ROA advice acceptance. Private evidence; never cash/fill acceptance."""
import argparse
from datetime import datetime, timezone
from fractions import Fraction as F
import json
from pathlib import Path
import re
from urllib.request import urlopen
from zoneinfo import ZoneInfo
from urllib.error import HTTPError


def review(before, config, snapshot, after, *, now):
    errors=[]
    def check(ok,reason):
        if not ok:errors.append(reason)
    result={'status':'FAILED','api_advice_passed':False,'page_verified':False,'cash_write_verified':False,'fill_verified':False,'errors':errors,'snapshot_status':snapshot.get('status'),'scope':'INDEPENDENT_API_CONSTRAINTS_NOT_TARGET_HASH_RECOMPUTATION'}
    try:
        account=before['account']
        check(before==after,'ACCOUNT_RESPONSE_CHANGED')
        check(snapshot.get('account')==account,'SNAPSHOT_ACCOUNT_MISMATCH')
        check(config.get('active') is True and config.get('strategy_kind')=='ROA_DEFENSIVE_V1','ROA_NOT_ACTIVE')
        check(bool(config.get('strategy_epoch')) and snapshot.get('strategy_epoch')==config['strategy_epoch'],'EPOCH_MISMATCH')
        check(snapshot.get('account_revision')==account['revision'],'REVISION_MISMATCH')
        check(snapshot.get('orders_created') is False,'ORDERS_CREATED')
        if errors:return result
        if snapshot.get('status')!='READY' or snapshot.get('executable') is not True:
            result.update(status='WAIT_EVENT',reason=snapshot.get('reason',snapshot.get('status')))
            return result
        check(account.get('cash_confirmation_valid') is True and account.get('execution_ready') is True,'ACCOUNT_NOT_EXECUTION_READY')
        check(snapshot.get('advice_ready') is True,'ADVICE_NOT_READY')
        for key in ('target_id','proposal_id'):
            check(isinstance(snapshot.get(key),str) and bool(re.fullmatch('[0-9a-f]{64}',snapshot[key])),key.upper()+'_INVALID')
        def time(value):
            value=datetime.fromisoformat(value.replace('Z','+00:00'))
            if value.tzinfo is None:raise ValueError('NAIVE_TIME')
            return value
        check(snapshot['phase'] in ('OPEN','CLOSE'),'INVALID_PHASE')
        check(snapshot['signal_date']<snapshot['execution_session'],'SIGNAL_SESSION_ORDER')
        check(now.astimezone(ZoneInfo('America/New_York')).date().isoformat()==snapshot['execution_session'],'EXECUTION_SESSION_MISMATCH')
        start,end,expiry=[time(snapshot[k]) for k in ('valid_from','valid_until','quote_valid_until')]
        check(start.astimezone(ZoneInfo('America/New_York')).date().isoformat()==snapshot['execution_session'] and end.astimezone(ZoneInfo('America/New_York')).date().isoformat()==snapshot['execution_session'],'WINDOW_SESSION_MISMATCH')
        check(start<=now<end and now<expiry<=end,'WINDOW_OR_QUOTE_EXPIRED')
        difference=snapshot['difference'];binding=difference['binding']
        check(difference['schema']=='STRATEGY_MANUAL_CASH_DIFFERENCE_V1','DIFFERENCE_SCHEMA')
        check(difference['account_id']==config['account_id'] and difference['account_revision']==account['revision'],'DIFFERENCE_ACCOUNT_MISMATCH')
        check(binding['account_id']==config['account_id'] and binding['account_revision']==account['revision'],'BINDING_ACCOUNT_MISMATCH')
        for sid, mark in binding['marks'].items():
            observed=time(mark['observed_at']);limit=binding['limits'][sid]
            check(0<=(now-observed).total_seconds()<=120,'STALE_OR_FUTURE_QUOTE')
            check(mark['security_id']==sid and mark['currency']=='USD' and mark['price_basis']=='current' and F(mark['price'])>0,'QUOTE_IDENTITY_OR_PRICE')
            check(limit['security_id']==sid and limit['price_basis']=='current' and limit['observed_at']==mark['observed_at'],'LIMIT_QUOTE_MISMATCH')
        holdings={r['security_id']:r['quantity'] for r in account['holdings']}
        orders=difference['new_orders'];rows=snapshot['rows']
        check(len({r['security_id'] for r in rows})==len(rows),'DUPLICATE_ROWS')
        check(len({r['security_id'] for r in orders})==len(orders),'DUPLICATE_ORDERS')
        targets=snapshot['target_quantities']
        check(all(type(q)is int and q>=0 for q in targets.values()),'INVALID_TARGET_QUANTITY')
        rate=F(binding['fee_bps'])/10000;cost=F(0)
        check(rate==0,'UNEXPECTED_FEE_POLICY')
        pending_sell={};pending_buy={}
        for order in account['orders']:
            check(type(order['remaining_quantity']) is int and order['remaining_quantity']>0 and order['quantity']==order['filled_quantity']+order['remaining_quantity'],'INVALID_OPEN_ORDER')
            if order['side']=='SELL':pending_sell[order['security_id']]=pending_sell.get(order['security_id'],0)+order['remaining_quantity']
            elif order['side']=='BUY':pending_buy[order['security_id']]=pending_buy.get(order['security_id'],0)+order['remaining_quantity']
        for row in rows:
            check(type(row['held'])is int and row['held']==holdings.get(row['security_id'],0),'HELD_MISMATCH')
            check(row['target_quantity']==targets.get(row['security_id'],0),'TARGET_ROW_MISMATCH')
        for order in orders:
            sid=order['security_id'];quantity=order['quantity'];price=F(order['limit_price'])
            check(type(quantity)is int and quantity>0,'INVALID_ORDER_QUANTITY')
            check(price==F(binding['limits'][sid][order['side'].lower()]),'ORDER_BOUND_LIMIT_MISMATCH')
            check(price>0 and (price*100).denominator==1,'INVALID_CENT_LIMIT')
            matching=[r for r in rows if r['security_id']==sid]
            check(len(matching)==1 and all(matching[0][key]==order[key] for key in ('side','quantity','limit_price')),'ORDER_ROW_MISMATCH')
            projected=holdings.get(sid,0)+pending_buy.get(sid,0)-pending_sell.get(sid,0)
            check(quantity<=max((targets.get(sid,0)-projected) if order['side']=='BUY' else (projected-targets.get(sid,0)),0),'ORDER_EXCEEDS_TARGET_DIFFERENCE')
            if order['side']=='SELL':check(quantity+pending_sell.get(sid,0)<=holdings.get(sid,0),'SELL_EXCEEDS_HOLDINGS')
            elif order['side']=='BUY':cost+=quantity*price*(1+rate)
            else:check(False,'INVALID_SIDE')
        check({r['security_id'] for r in rows if r['side'] in ('BUY','SELL')}=={r['security_id'] for r in orders},'EXTRA_ACTION_ROW')
        available=F(account['available_cash'])
        check(0<=cost<=available,'BUY_EXCEEDS_CONFIRMED_CASH')
        check(cost==F(difference['new_buy_cash_required']),'BUY_COST_MISMATCH')
        check(F(difference['spendable_cash'])==available,'AVAILABLE_CASH_MISMATCH')
        result['new_buy_cash_required']=str(cost)
        if not errors:result.update(status='PASS_API_ADVICE',api_advice_passed=True)
    except (KeyError,ValueError,TypeError,ZeroDivisionError) as error:
        errors.append('INVALID_RESPONSE:'+str(error))
    return result


def capture(base_url, output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    records={};http_status={}
    for name,path in [('before','/api/strategy-account'),('config','/api/strategy-roa/config'),('snapshot','/api/strategy-roa/snapshot'),('after','/api/strategy-account')]:
        try:
            response=urlopen(base_url.rstrip('/')+path,timeout=120)
        except HTTPError as error:response=error
        http_status[name]=response.code
        raw=response.read();(output/(name+'.json')).write_bytes(raw)
        records[name]=json.loads(raw)
    result=review(**records,now=datetime.now(timezone.utc))
    result['http_status']=http_status
    # A service error is not a normal wait for the trading window, even when
    # its fallback JSON contains a WAIT status and an unchanged account.
    if any(code!=200 for code in http_status.values()):
        result.update(status='FAILED',api_advice_passed=False);result['errors'].append('HTTP_STATUS_INVALID')
    (output/'summary.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--base-url',default='http://127.0.0.1:8010');parser.add_argument('--output',default='tmp/roa_live_advice_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    args=parser.parse_args();print(json.dumps(capture(args.base_url,args.output)))
