"""Independent exact replay of recorded auction accounting; no strategy search."""
from pathlib import Path
from fractions import Fraction as F
from hashlib import sha256
from datetime import datetime
from zoneinfo import ZoneInfo
import gzip,json,time
ROOT=Path(__file__).resolve().parents[2]


def audit(book,days,prices,rosters,dividends,splits,label):
    cash=F(20000);positions={};due=[];turnover=F(0);peak=cash;dd=F(0);orders=[];rejects=[];actions=[];ledger=[]
    slip=F(book['slippage_bps'],10000);fee=F(book['commission_bps'],10000);last=None;bought=False
    def price(s,d,f):
        v=F(prices[s][d][f]);assert v>0;return v
    def snapshot(d,phase,field):
        nonlocal peak,dd
        receivable=sum((r['amount'] for r in due),F(0));equity=cash+receivable+sum((q*price(s,d,field) for s,q in positions.items() if q),F(0))
        peak=max(peak,equity);dd=max(dd,1-equity/peak)
        ledger.append(dict(day=d,phase=phase,equity=str(equity),cash=str(cash),holdings=dict(positions),receivable=str(receivable)))
    for index,day in enumerate(days[1:],1):
        previous=days[index-1];roster=max((r for r in rosters if r['decision']<=previous),key=lambda r:r['decision'])
        assert len(set(roster['selected']))==len(roster['selected'])<=10
        for event in splits:
            if event['date']!=day:continue
            n=positions.pop(event['old_sid'],0)
            if n:
                changed=n*F(event['ratio']);assert changed.denominator==1
                positions[event['new_sid']]=positions.get(event['new_sid'],0)+int(changed)
                actions.append(dict(day=day,old_sid=event['old_sid'],new_sid=event['new_sid'],old_quantity=n,new_quantity=int(changed)))
        for event in dividends:
            if event['ex_date']==day and positions.get(event['sid'],0):
                due.append(dict(amount=positions[event['sid']]*F(event['amount']),pay=event.get('payment_date'),sid=event['sid'],ex_date=day))
        snapshot(day,'OPEN_BEFORE_ORDERS','open')
        change=roster['decision']!=last;final=index==len(days)-1
        if book['mode']=='overnight' or change or final:
            for sid,n in sorted(positions.items()):
                if not n:continue
                fill=price(sid,day,'open')*(1-slip);gross=n*fill;cost=gross*fee
                cash+=gross-cost;turnover+=gross
                orders.append(dict(day=day,phase='OPEN',side='SELL',sid=sid,quantity=n,price=str(fill),commission=str(cost)))
            positions={}
        snapshot(day,'OPEN_AFTER_ORDERS','open')
        if not final and (book['mode']=='overnight' or change or (label=='QQQ_HOLD' and not bought)):
            allocation=cash/len(roster['selected']) if roster['selected'] else F(0)
            for sid in roster['selected']:
                previous_close=price(sid,previous,'close');n=int(allocation/(previous_close*(1+slip)*(1+fee)))
                if n==0:rejects.append(dict(day=day,sid=sid,reason='ZERO_INTEGER_QUANTITY'));continue
                fill=price(sid,day,'close')*(1+slip);gross=n*fill;cost=gross*fee
                if gross+cost>allocation:
                    rejects.append(dict(day=day,sid=sid,quantity=n,reason='FIXED_SLOT_CASH_EXCEEDED'));continue
                cash-=gross+cost;turnover+=gross;positions[sid]=positions.get(sid,0)+n;bought=True
                orders.append(dict(day=day,phase='CLOSE',side='BUY',sid=sid,quantity=n,sizing_previous_close=str(previous_close),price=str(fill),commission=str(cost),decision=roster['decision']))
        remaining=[]
        for item in due:
            if item['pay'] is not None and item['pay']<=day:cash+=item['amount']
            else:remaining.append(item)
        due=remaining;assert cash>=0;snapshot(day,'CLOSE','close');last=roster['decision']
    assert orders==book['orders'],'ORDER_OR_FEE_MISMATCH'
    assert rejects==book['rejections'],'REJECTION_OR_RETRY_MISMATCH'
    assert actions==book['splits'],'IDENTITY_ACTION_MISMATCH'
    assert ledger==book['ledger'],'DAILY_CASH_SHARES_EQUITY_MISMATCH'
    assert F(book['turnover'])==turnover and F(book['cash'])==cash and book['holdings']==positions
    assert book['receivables']==[dict(x,amount=str(x['amount'])) for x in due]
    assert F(book['drawdown'])==dd and book['terminal_equity']==ledger[-1]['equity']
    elapsed_days=(datetime.fromisoformat(days[-1])-datetime.fromisoformat(days[0])).days
    return dict(status='PASS',sessions=len(days)-1,endpoint_marks=len(ledger),orders=len(orders),rejections=len(rejects),terminal=float(F(book['terminal_equity'])),cagr_pct=(float(F(book['terminal_equity'])/20000)**(365.25/elapsed_days)-1)*100,dd_pct=float(dd)*100,turnover=float(turnover),ending_receivable=float(sum((x['amount'] for x in due),F(0))))


def main():
    start=time.monotonic();out=ROOT/'tmp/overnight_fixed_20261105_v1';contract=json.loads((out/'contract.json').read_bytes());pins={**contract['source_expected_pins'],**contract['code_pins']}
    for n,h in pins.items():assert sha256((ROOT/n).read_bytes()).hexdigest()==h,n
    inv=json.loads((ROOT/'tmp/overnight_preflight_20261105/result.json').read_bytes());qp={};qdiv={}
    for name in ('tmp/qqq_month_end_warmup_20261026_v1/QQQ.response.bin','data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin'):
        raw=(ROOT/name).read_bytes();body=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)['chart']['result'][0]
        for i,t in enumerate(body['timestamp']):
            day=datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat();row={k:str(body['indicators']['quote'][0][k][i]) for k in ('open','close')};assert day not in qp or qp[day]==row;qp[day]=row
        for event in body.get('events',{}).get('dividends',{}).values():
            day=datetime.fromtimestamp(event['date'],ZoneInfo('America/New_York')).date().isoformat();assert day not in qdiv or F(qdiv[day])==F(str(event['amount']));qdiv[day]=str(event['amount'])
    results=[];bookpins={}
    for row in inv['results']:
        window=row['window'];base='recent_continuous_baseline_20261026_v7' if window=='2021_2023' else 'old_continuous_baseline_20261026_v9';document=json.loads((ROOT/'tmp'/base/'execution_inputs.json').read_bytes());days=document['assembled']['session_dates']
        ordinary=[dict(sid=e['security_id'],ex_date=e['ex_date'],payment_date=e['payment_date'],amount=e['amount_per_share']) for e in document['dividend_events']]
        actions=[dict(date=e['date'],old_sid=e['security_id'],new_sid=e['new_security_id'],ratio=str(F(e['new_shares'])/F(e['old_shares']))) for e in document['assembled']['actions']]
        for label in ('O1','SAME_ROSTER_HOLD','O2_QQQ','QQQ_HOLD'):
            qqq=label in ('O2_QQQ','QQQ_HOLD');prices={'QQQ':qp} if qqq else document['ohlc'];rosters=[dict(decision=days[0],selected=['QQQ'])] if qqq else row['rosters'];divs=[dict(sid='QQQ',ex_date=d,amount=a,payment_date=None) for d,a in qdiv.items()] if qqq else ordinary
            for slip,fee in contract['scenarios']:
                name=f'{window}_{label}_{slip}_{fee}.json';raw=(out/name).read_bytes();bookpins[name]=sha256(raw).hexdigest();book=json.loads(raw)
                proof=audit(book,days,prices,rosters,divs,[] if qqq else actions,label);proof.update(window=window,label=label,slippage_bps=slip,commission_bps=fee);results.append(proof)
    for n,h in pins.items():assert sha256((ROOT/n).read_bytes()).hexdigest()==h,n
    result=dict(status='PASS',books_checked=len(results),results=results,source_pins_verified=len(pins),book_hashes=bookpins,elapsed_seconds=time.monotonic()-start,review_script_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),limitations=['Fixed baseline rosters, not dynamic account selection','Endpoint drawdown, not intraday minimum','QQQ dividends without payment dates remain locked receivables, not reinvested total-return index','Ideal auction rejection and same-day sale-proceeds reuse are not broker-certified'])
    (out/'independent_review.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in result.items() if k not in ('results','book_hashes')}));print(json.dumps([r for r in results if r['slippage_bps']==5 and r['commission_bps']==0]))

if __name__=='__main__':main()
