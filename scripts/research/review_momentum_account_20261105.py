"""Independent saved-ledger arithmetic; no candidate execution or sizing call."""
import argparse,json,sys
from pathlib import Path
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
from backtest.research_exact_fraction_json import loads
ROOT=Path(__file__).resolve().parents[2]
sys.set_int_max_str_digits(100000)
def need(ok,why):
    if not ok:raise ValueError(why)
def read(p):return loads(Path(p).read_text(encoding='utf8'))
def hashfile(p):return sha256(Path(p).read_bytes()).hexdigest()

def audit(directory):
    book=read(directory/'book.json');contract=read(directory/'contract.json');doc=read(directory/'execution_inputs.json')['document'];a=doc['assembled'];days=a['session_dates'];bars=doc['ohlc']
    summary=read(directory/'summary.json')
    need(summary['status']=='COMPLETE' and summary['completed_sessions']==summary['required_sessions']==len(days)-1 and summary['search_calls']==0 and summary['settlement_delay']==contract['settlement_delay'],'SUMMARY_BINDING')
    need(book['status']=='COMPLETE','COMPLETE_REQUIRED')
    for p,h in contract['source_hashes'].items():need(hashfile(ROOT/p)==h,'PIN:'+p)
    # Reassemble frozen source evidence only, never run the economic engine.
    from scripts.research import run_momentum_account_20261105 as launcher
    freeze=json.loads((ROOT/'research_contracts/momentum_account_execution_20261105/freeze.json').read_bytes())
    launcher.inventory.PINS.clear()
    original,prices,review,legacy,proof=launcher.inventory.inputs(contract['window'],launcher.read(freeze['inventory_base_freeze']))
    pins={**launcher.inventory.PINS,**freeze['source_hashes']}
    original,review=launcher.prepare_actions(window=contract['window'],document=original,prices=prices,review=review,pins=pins,freeze=freeze)
    for plan in original['assembled']['monthly_inputs']:plan['source_hashes'].update({launcher.ROSTER_PATH:launcher.ROSTER_SHA,launcher.CORE:pins[launcher.CORE]})
    need(original==doc and review==read(directory/'execution_inputs.json')['review'] and pins==contract['source_hashes'],'FROZEN_DERIVED_INPUT_RECONSTRUCTION')
    roster=json.loads((ROOT/'tmp/cross_sectional_momentum_static_20261105/result.json').read_bytes())
    rows={r['decision_date']:r for r in roster['rows'] if r['window']==contract['window']}
    plans={p['decision_date']:p for p in a['monthly_inputs']}
    need(set(rows)==set(plans),'MONTH_GRID');need(a['actions']==a['provider_actions'],'PAIRED_ACTIONS')
    need(not a['distribution_events'] and not a['cash_stock_merger_events'],'UNSUPPORTED_RIGHTS')
    need([r['date'] for r in book['daily_ledger']]==days[1:] and len(book['provider_audit'])==len(days)-1,'FULL_SESSIONS')
    need(F(book['fee_bps'])==0 and F(book['slippage_bps'])==5 and book['search_calls']==0,'COSTS_SEARCH')
    cash=F(20000);shares={};peak=F(20000);dd=F(0);baseline={};peaks={};exited=set();accrued={};paid={};claims={};released={};selection_count=0
    events={e['event_id']:e for e in doc['dividend_events']};need(len(events)==len(doc['dividend_events']),'DUPLICATE_DIVIDEND')
    delay=contract['settlement_delay'];need(type(delay) is int and delay in (0,1,5),'DELAY');fills=[];order_ids=set()
    for i,(row,audit) in enumerate(zip(book['daily_ledger'],book['provider_audit']),1):
        day=days[i];decision=days[i-1];selected=audit.get('selection')
        if selected is not None:
            need(decision in plans,'SELECTION_DATE');selection_count+=1;r=rows[decision];binding=selected['binding']
            need(selected['roster']==r and binding['shares']==shares and F(binding['available_cash'])==cash,'REAL_ACCOUNT_ROSTER')
            saved=read(directory/(decision+'.selection.json'));need(saved['selected']==selected and saved['arguments']['account_state']['shares']==shares and F(saved['arguments']['account_state']['cash'])==cash,'SELECTION_FILE_BINDING')
            need(binding['decision_date']==decision and binding['source_hashes']==plans[decision]['source_hashes'],'SELECTION_PINS')
            equity=cash+sum((q*F(a['close_prices'][s][decision]) for s,q in shares.items() if q),F(0))
            need(F(selected['investable_equity'])==equity,'TRADABLE_CAPITAL')
            domain=plans[decision]['search_arguments']['metadata'];ids=[x['security_id'] for x in r['selected']]
            need(len(ids)==len(set(ids))==10 and len({x['issuer_id'] for x in r['selected']})==10,'TEN_UNIQUE')
            need(all(domain[x['security_id']]['issuer_id']==x['issuer_id'] for x in r['selected']),'LEGAL_ISSUERS')
            baseline={s:int((equity/10)//F(a['close_prices'][s][decision])) for s in ids} if r['gate']['risk_on'] else {}
            need(selected['target_quantities']==baseline,'INDEPENDENT_INTEGER_TARGET');peaks={};exited=set()
            gate=read(directory/(decision+'.exposure.json'));need(gate['admitted'] and not gate['unmapped_events'] and not gate['missing_action_streams'],'ACTION_GATE')
        else:
            for e in a['actions']:
                if e['date']!=decision:continue
                s=e['security_id']
                if e['type']=='merger':baseline.pop(s,None);peaks.pop(s,None);exited.discard(s)
                elif s in baseline:
                    ratio=F(e['new_shares'])/F(e['old_shares']);n=e.get('new_security_id',s);quantity=baseline.pop(s)*ratio
                    need(quantity.denominator==1,'RISK_FRACTIONAL');baseline[n]=int(quantity)
                    if s in peaks:peaks[n]=peaks.pop(s)/ratio
                    if s in exited:exited.remove(s);exited.add(n)
        need(audit['monthly_ceiling']==baseline,'MONTHLY_CEILING')
        for s in baseline:
            price=F(a['close_prices'][s][decision]);peaks[s]=max(peaks.get(s,price),price)
            if price*5<=peaks[s]*4:exited.add(s)
        target={s:0 if s in exited else q for s,q in baseline.items()}
        need(audit['target_shares']==target,'PEAK_EXIT_AND_LOCK')
        if baseline:
            state=audit['risk_overlay']['state'];need({s:F(v) for s,v in state['peaks'].items()}==peaks and set(state['exited'])==exited,'RISK_INTERNAL_STATE')
        wanted=sorted((s,'BUY' if target.get(s,0)>shares.get(s,0) else 'SELL',abs(target.get(s,0)-shares.get(s,0))) for s in set(target)|set(shares) if target.get(s,0)!=shares.get(s,0))
        orders=deepcopy(audit['orders']);need(sorted((o['security_id'],o['side'],o['quantity']) for o in orders)==wanted,'ORDER_TARGET_DIFF')
        for o in orders:
            need(o['id'] not in order_ids,'DUPLICATE_ORDER_ID');order_ids.add(o['id'])
        for o in orders:need(o['decision_date']==decision and o['active_date']==day and F(o['decision_mark'])==F(a['close_prices'][o['security_id']][decision]),'NEXT_OPEN_MARK')
        for key,e in events.items():
            if e['ex_date']==day:accrued[key]=shares.get(e['security_id'],0)*F(e['amount_per_share'])*(1-F(e['withholding_rate']))
        for e in a['actions']:
            if e['date']!=day:continue
            s=e['security_id'];kind=e['type']
            if kind=='merger':
                if shares.get(s,0):claims[e['event_id']]=dict(amount=shares[s]*F(e['share_cash']),due=days[i+delay] if i+delay<len(days) else None)
                shares[s]=0;orders=[o for o in orders if o['security_id']!=s]
            else:
                need(kind in ('split','split_identity'),'UNKNOWN_ACTION');n=e.get('new_security_id',s);ratio=F(e['new_shares'])/F(e['old_shares']);q=shares.get(s,0)*ratio
                need(q.denominator==1,'FRACTIONAL_HOLDING')
                if shares.get(s,0) or any(o['security_id']==s for o in orders) or n!=s:shares[s]=0 if n!=s else int(q);shares[n]=int(q)
                for o in orders:
                    if o['security_id']==s:
                        q=o['quantity']*ratio;need(q.denominator==1,'FRACTIONAL_ORDER');o['quantity']=int(q);o['security_id']=n
        for o in sorted((o for o in orders if o['side']=='SELL'),key=lambda o:o['id']):
            s=o['security_id'];q=o['quantity'];need(q<=shares.get(s,0),'OVERSELL');cash+=q*F(bars[s][day]['open'])*F(1999,2000);shares[s]-=q
            fills.append((day,o['id'],s,'SELL',q,F(bars[s][day]['open'])*F(1999,2000),F(0),cash))
        buys=sorted((o for o in orders if o['side']=='BUY'),key=lambda o:o['id']);cost=sum((o['quantity']*F(bars[o['security_id']][day]['open'])*F(2001,2000) for o in buys),F(0));scale=min(F(1),cash/cost) if cost else F(0)
        for o in buys:
            s=o['security_id'];q=int(o['quantity']*scale);cash-=q*F(bars[s][day]['open'])*F(2001,2000);shares[s]=shares.get(s,0)+q
            if q:fills.append((day,o['id'],s,'BUY',q,F(bars[s][day]['open'])*F(2001,2000),F(0),cash))
        for key,value in accrued.items():
            due=events[key]['payment_date']
            if key not in paid and due is not None and due<=day:cash+=value;paid[key]=day
        for key,claim in claims.items():
            if key not in released and claim['due']==day:cash+=claim['amount'];released[key]=day
        pending=sum((v for k,v in accrued.items() if k not in paid),F(0));merger=sum((v['amount'] for k,v in claims.items() if k not in released),F(0));stock=sum((q*F(bars[s][day]['close']) for s,q in shares.items() if q),F(0));equity=cash+stock+pending+merger
        need(cash>=0 and F(row['cash'])==cash and row['shares']==shares,'DAILY_CASH_SHARES:'+day)
        need(F(row['dividend_receivable'])==pending and F(row['receivable'])==merger and F(row['stock_value'])==stock and F(row['equity'])==equity,'DAILY_EQUITY_RIGHTS:'+day)
        need(not row['distribution_rights'] and not row['merger_entitlements'] and F(row['external_flow'])==0,'UNEXPECTED_RIGHTS_FLOW')
        peak=max(peak,equity);dd=max(dd,1-equity/peak)
    need(selection_count==len(rows)==book['target_sizing_calls'],'ALL_SELECTIONS')
    need(summary['target_sizing_calls']==selection_count,'SUMMARY_SIZING_COUNT')
    actual_fills=[(x['date'],x['id'],x['security_id'],x['side'],x['quantity'],F(x['price']),F(x['fee']),F(x['cash_after'])) for x in book['order_log'] if x['event']=='ASSUMED_NEXT_OPEN_FILLED']
    need(actual_fills==fills,'EXACT_TRADE_LOG')
    need(F(book['cash'])==cash and book['shares']==shares and F(book['fees'])==0,'TERMINAL')
    need(F(book['total_return'])==equity/F(20000)-1 and F(book['drawdown']['maximum_close_drawdown'])==dd,'RETURN_DRAWDOWN')
    dl=book['dividend_ledger'];need(set(dl['events'])==set(accrued),'DIVIDEND_SET')
    for key,value in accrued.items():need(dl['events'][key]['event']==events[key] and F(dl['events'][key]['net'])==value,'DIVIDEND_EVENT')
    need(len(dl['payments'])==len({p['event_id'] for p in dl['payments'].values()})==len(paid),'DUPLICATE_PAYMENT')
    need({p['event_id']:p['session_date'] for p in dl['payments'].values()}==paid and F(dl['receivable'])==pending and F(dl['paid_cash'])==sum((accrued[k] for k in paid),F(0)),'PAYMENTS')
    releases=book['cash_merger_settlement']['releases'];need({x['event_id']:x['date'] for x in releases}==released and all(F(x['amount'])==claims[x['event_id']]['amount'] for x in releases),'MERGER_RELEASES')
    need(len(releases)==len({x['event_id'] for x in releases})==len(released),'DUPLICATE_MERGER_RELEASE')
    return dict(status='INDEPENDENT_MOMENTUM_ACCOUNT_PASS',window=contract['window'],sessions=len(days)-1,monthly_targets=selection_count,trades_checked=len(fills),final_equity=str(equity),maximum_drawdown=str(dd),delay_sessions=delay,merger_claims=len(claims),scope='Independent exact daily cash/shares/rights/execution arithmetic, fixed authenticated roster integer sizing and original 20% monthly peak locks. No candidate function replay. Roster ranking and market gate rely on frozen separately reviewed static artifact; conditional action evidence retained.',economic_replays=0)

def run(output):
    directory=ROOT/output
    try:report=audit(directory)
    except Exception as error:report=dict(status='FAILED',reason=str(error));raise_error=error
    else:raise_error=None
    paths=[directory/'book.json',directory/'contract.json',directory/'execution_inputs.json',Path(__file__),ROOT/'backtest/research_exact_fraction_json.py',ROOT/'tmp/cross_sectional_momentum_static_20261105/result.json']
    paths += [directory/'summary.json',*sorted(directory.glob('*.selection.json')),*sorted(directory.glob('*.exposure.json'))]
    paths += [ROOT/'research_contracts/momentum_account_execution_20261105/freeze.json']
    report['source_hashes']={p.relative_to(ROOT).as_posix():hashfile(p) for p in paths};report['book_sha256']=hashfile(directory/'book.json')
    (directory/'independent_review.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report))
    if raise_error:raise raise_error

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);run(parser.parse_args().output)
