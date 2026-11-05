"""Independent cap20 selection/account audit; no candidate search/apply or economic replay."""
import argparse,json,math,sys
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
from backtest.research_exact_fraction_json import loads
from scripts.research import review_downside_account_20261105 as prior
from scripts.research.review_downside_account_20261105 import frontier,canonical,evidence_hash,product_hash,risk
ROOT=Path(__file__).resolve().parents[2]
sys.set_int_max_str_digits(100000)
def require(ok,reason):
 if not ok:raise ValueError(reason)
need=require
def read(path):return loads(Path(path).read_bytes())
def digest(path):return sha256(Path(path).read_bytes()).hexdigest()
def check(pins):
 for path,h in pins.items():require(digest(ROOT/path)==h,'SOURCE_CHANGED:'+path)
def score(q,args,enforce_cap=True):
 result=prior.score(q,args,False)
 if enforce_cap:require(all(n*F(args['prices'][s])*5<=F(args['entered_cash']) for s,n in q.items()),'CAP20_TOTAL_TRADABLE')
 return result

def review_selection(selected,sidecar,returns,reference,pins):
    raw=selected['raw_selection'];args=frontier._binding(raw)
    require(selected['method']=='SAME_CALL_OBSERVED_DOWNSIDE_QQQ_CAP20_V1','SELECTION_METHOD')
    require(set(returns)==set(args['prices']) and len(args['training_scenarios'])==12,'RETURN_DOMAIN')
    dates=list(reference)
    require(args['scenario_dates']==dates[20::21],'SCENARIO_DATES')
    for sid,rows in returns.items():
        require(list(rows)==dates and all(F(v)>-1 for v in rows.values()),'COMMON_POSITIVE_GROSS')
        for i,row in enumerate(args['training_scenarios']):
            require(math.prod(1+F(rows[d]) for d in dates[i*21:(i+1)*21])==F(row[sid]),'DAILY_12_SCENARIO_COORDINATES')
    require(all(F(v)>-1 for v in reference.values()),'QQQ_POSITIVE_GROSS')
    require(evidence_hash({k:v for k,v in sidecar.items() if k!='integrity_sha256'})==sidecar['integrity_sha256']==raw['downside_sidecar_sha256'],'SIDECAR_DIGEST')
    expected_binding=dict(capital_decision_id=raw['decision_id'],capital_binding_sha256=evidence_hash(raw['binding']),
        search_arguments_sha256=evidence_hash(args),capital_source_hashes=raw['binding']['source_hashes'],
        research_source_hashes=pins,stock_return_coordinates_sha256=evidence_hash(returns),qqq_coordinates_sha256=evidence_hash(reference))
    require(sidecar['evidence_binding']==expected_binding,'SIDECAR_DYNAMIC_BINDING')
    require(sidecar['complete'] is True and sidecar['max_holdings']==10 and sidecar['single_target_cap']=='1/5','COMPLETE_MAX10_CAP20')
    counts=sidecar['coverage'];phases=sidecar['phase_counts'];search=raw['search_result']
    require(all(type(v) is int and v>=0 for v in counts.values()),'COUNT_DOMAIN')
    require(counts['risk_evaluated']==counts['capped_unique']-counts['over_holdings_limit']<=10000,'COVERAGE_COUNTS')
    require(counts['raw_unique_observed']>=counts['capped_unique']>=counts['over_holdings_limit'],'COVERAGE_ORDER')
    require(phases['base']==search['objective_evaluations'] and phases['comparison']==sum(search['continuous_comparison']['exact_evaluations'][k] for k in ('saved_unique','new_unique')),'PHASE_COUNTS')
    # Reconstruct original V27 rerank target independently from saved frontier.
    cap=lambda q:{s:min(n,int(F(args['entered_cash'])/(2*F(args['prices'][s])))) for s,n in q.items()}
    base=cap(raw['target_quantities']);base_score=prior.score({s:q for s,q in base.items() if q},args)
    baskets={tuple(sorted((s,q) for s,q in cap(row['quantities']).items() if q)) for row in search['best_by_k'].values()}
    improved=[q for q in baskets if prior.score(dict(q),args)['product']>base_score['product']]
    incumbent=dict(max(improved,key=lambda q:(prior.score(dict(q),args)['product'],-prior.score(dict(q),args)['notional'],q))) if improved else base
    original=deepcopy(selected)
    original.update(method='SAME_CALL_SAVED_FRONTIER_CAP50_STRICT_RERANK_V1',target_quantities=incumbent,rerank_audit=selected['original_rerank_audit'])
    bind=dict(schema=original['method'],original_decision_id=raw['decision_id'],original_raw_selection_sha256=canonical(raw),
        target_quantities=incumbent,base_capped_target_quantities=base,monthly_cap_fraction='1/2',rerank_audit=original['rerank_audit'])
    original.update(rerank_binding=bind,rerank_decision_id=canonical(bind))
    proof=frontier.review_selection(original,rerank_enabled=True)
    cap=lambda q:{s:min(n,int(F(args['entered_cash'])/(5*F(args['prices'][s])))) for s,n in q.items()}
    incumbent={s:q for s,q in cap(incumbent).items() if q}
    incumbent_positive=incumbent
    incumbent_score=score(incumbent_positive,args)
    inc_pass,inc_risk,qqq_risk=risk(incumbent,args,returns,reference)
    inc_pass=inc_pass and len(incumbent_positive)<=10
    records=[sidecar['cash'],*sidecar['eligible_best_by_k'].values()]
    require(sidecar['cash']['target_quantities']=={} and sidecar['cash_fallback_seeded'] is True,'CASH_FALLBACK')
    for key,record in sidecar['eligible_best_by_k'].items():
        require(str(record['actual_k'])==key and 1<=int(key)<=10,'CARDINALITY_KEY')
    assessed=[]
    for record in records:
        quantities=record['target_quantities'];s=score(quantities,args)
        require(len(quantities)==record['actual_k']<=10,'MAX10_ACTUAL')
        require(s['product']==record['exact_product'] and s['notional']==record['notional'] and s['residual_cash']==record['residual_cash'],'SIDECAR_EXACT_SCORE')
        passed,value,_=risk(quantities,args,returns,reference)
        require(passed,'EXACT_DOWNSIDE_GATE')
        low,high=map(F,record['downside_interval']);require(low<=value<=high,'DOWNSIDE_INTERVAL')
        if record['source_phase']=='EXPLICIT_CASH_FALLBACK_NOT_SEARCH_OBSERVATION':
            require(not quantities and record['source_evaluation_index'] is None,'CASH_PROVENANCE')
        else:
            require(record['source_phase'] in ('base','comparison') and type(record['source_evaluation_index']) is int and record['source_evaluation_index']>=0,'OBSERVED_PROVENANCE')
            raw_quantities=dict(record['raw_signature']);score(raw_quantities,args,False)
            require({s:q for s,q in cap(raw_quantities).items() if q}==quantities,'OBSERVED_CAP_MAPPING')
        assessed.append((quantities,s))
    eligible=[(q,s) for q,s in assessed if not inc_pass or s['product']>incumbent_score['product']]
    chosen,chosen_score=max(eligible,key=lambda pair:(pair[1]['product'],-pair[1]['notional'],tuple(sorted(pair[0].items())))) if eligible else (incumbent,incumbent_score)
    require(selected['target_quantities']==chosen,'INDEPENDENT_DOWNSIDE_WINNER')
    audit=selected['downside_audit']
    require(audit==dict(incumbent='ACTUAL_V27_CAP50_RERANK_INCUMBENT_PROJECTED_TO_CAP20_RECHECKED',incumbent_admitted=inc_pass,
        incumbent_product_sha256=product_hash(incumbent_score['product']),selected_product_sha256=product_hash(chosen_score['product']),coverage=counts,
        tie_rule='ADMITTED_ACTUAL_V27_INCUMBENT_RETAINED_UNLESS_STRICT_PRODUCT_IMPROVEMENT',holding_count_limit=10,single_target_cap='1/5',unallocated_policy='CASH_NO_RENORMALIZATION',source_authenticated=False),'DOWNSIDE_AUDIT')
    bind=dict(schema=selected['method'],original_rerank_decision_id=original['rerank_decision_id'],target_quantities=chosen,downside_audit=audit)
    require(selected['rerank_binding']==bind and selected['rerank_decision_id']==canonical(bind),'DOWNSIDE_SELECTION_BINDING')
    proof['target_quantities']=chosen
    return proof,dict(incumbent_admitted=inc_pass,incumbent_downside=str(inc_risk),qqq_downside=str(qqq_risk),
        retained_records_checked=len(records),target=chosen,full_observed_winner_dominance_proven=False)


def provenance(directory,contract,summary,book):
 from scripts.research import run_downside_cap20_account_20261105 as runner
 if contract.get('conditional_assumption_dependency'):
  if contract.get('conditional_assumption_dependencies'):
   from scripts.research.run_downside_cap20_alxn_june_exit_20261105 import make_runner
  else:
   from scripts.research.run_downside_cap20_alxn_assumption_20261105 import make_runner
  runner=make_runner();require(contract.get('production_admission') is False,'CONDITIONAL_NOT_PRODUCTION')
 check(contract['source_hashes']);check(contract.get('parent_file_hashes',{}))
 require(contract['schema']==runner.SCHEMA and contract['cap']=='1/5' and contract['max_holdings']==10,'CONTRACT_RULES')
 require(contract['seconds_per_window']==10800 and contract['seconds_per_month']==600 and summary['elapsed_seconds']<10800,'WINDOW_BUDGET')
 require(all(v<600 for v in summary['monthly_elapsed_seconds'].values()),'MONTH_BUDGET')
 evidence=read(directory/'additional_execution_evidence.json');names=[r['path'] for r in evidence]
 document,prices,review,legacy,proof,pins,windows,qprices,rebuilt=runner.prepare(contract['window'],names)
 require(pins==contract['source_hashes'] and rebuilt==evidence,'REBUILT_SOURCE_CLOSURE')
 require(read(directory/'execution_inputs.json')==dict(document=document,review=review),'EXACT_DERIVED_INPUTS_FROM_FROZEN_SOURCES')
 parent=runner.load_parent(contract.get('parent_output'))
 if parent:
  require(parent['hashes']==contract['parent_file_hashes'],'PARENT_HASH_CLOSURE')
  require(contract['inherited_seconds']==parent['summary']['elapsed_seconds'] and contract['inherited_searches']==parent['summary']['searches']['new'],'CUMULATIVE_PARENT_BUDGET')
  require(book['daily_ledger'][:len(parent['book']['daily_ledger'])]==parent['book']['daily_ledger'],'EXACT_PARENT_PREFIX')
  require(summary['elapsed_seconds']>=contract['inherited_seconds'],'NO_TIME_RESET')
  for day,saved in parent['records'].items():
   record=read(directory/(day+'.selection.json'))
   require(all(record[k]==saved['record'][k] for k in ('arguments','raw_selection','sidecar')) and record['research_source_hashes']==saved['owner'],'PARENT_SELECTION_RESEARCH_OWNER')
  ancestor=Path(contract['parent_output']);seen={directory.resolve()}
  while ancestor:
   folder=(ROOT/ancestor).resolve();require(folder not in seen,'PARENT_CYCLE');seen.add(folder)
   c=read(folder/'contract.json');check(c['source_hashes']);check(c.get('parent_file_hashes',{}))
   if c.get('scope')=='ACCOUNTING_ONLY_PREFLIGHT_REPLAY_NO_SEARCH':
    check(c['selection_research_source_hashes']);break
   ancestor=c.get('parent_output')
 else:require(contract['inherited_seconds']==0 and contract['inherited_searches']==0,'INITIAL_BUDGET')
 return document,review,prices,legacy,proof,windows,qprices,parent,runner

def audit(directory):
 contract=read(directory/'contract.json');summary=read(directory/'summary.json');book=read(directory/'book.json');late=contract['window']=='2024_2026';count=646 if late else 753;months=31 if late else 36
 require(summary['status']==book['status']=='COMPLETE' and summary['completed_sessions']==summary['required_sessions']==len(book['daily_ledger'])==count,'COMPLETE_FULL_WINDOW_REQUIRED')
 document,review,prices,legacy,proof,windows,qprices,parent,runner=provenance(directory,contract,summary,book);a=document['assembled'];days=a['session_dates'];bars=document['ohlc']
 require((days[0],days[-1])==(('2023-12-29','2026-07-30') if late else ('2020-12-31','2023-12-29')) and len(days)==count+1,'EXACT_INDEPENDENT_WINDOW')
 require(summary['searches']['new']==months and len(summary['monthly_elapsed_seconds'])==months,'COMPLETE_SEARCH_BUDGET')
 plans={p['decision_date']:p for p in a['monthly_inputs']};ends={d:(list(plans)[i+1] if i+1<len(plans) else days[-1]) for i,d in enumerate(plans)}
 require(len(plans)==months and a['actions']==a['provider_actions'],'PAIRED_ACTIONS_AND_MONTHS')
 require(not a['distribution_events'] and not a['cash_stock_merger_events'],'UNSUPPORTED_MIXED_RIGHTS')
 require([r['date'] for r in book['daily_ledger']]==days[1:] and len(book['provider_audit'])==count,'FULL_SESSIONS')
 require(F(book['fee_bps'])==0 and F(book['slippage_bps'])==5,'FIXED_COSTS')
 cash=F(20000);shares={};peak=F(20000);dd=F(0);baseline={};peaks={};exited=set();accrued={};paid={};claims={};released={};selection_count=0;selection_checks={};terminated=set()
 events={e['event_id']:e for e in document['dividend_events']};require(len(events)==len(document['dividend_events']),'DUPLICATE_DIVIDEND')
 fills=[];order_ids=set()
 for i,(row,provider) in enumerate(zip(book['daily_ledger'],book['provider_audit']),1):
  day=days[i];decision=days[i-1];selected=provider.get('selection')
  require(not any(shares.get(s,0) for s in terminated) and not any(o['security_id'] in terminated for o in provider['orders']),'TERMINATED_REAPPEARED')
  if selected is not None:
   require(decision in plans and decision not in selection_checks,'SELECTION_DATE');selection_count+=1;record=read(directory/(decision+'.selection.json'));saved=read(directory/(decision+'.decision.json'))
   require(saved['selected']==selected and record['raw_selection']==selected['raw_selection'],'SAVED_SELECTED_BINDING');binding=selected['raw_selection']['binding']
   require(binding['shares']==shares and F(binding['available_cash'])==cash,'DYNAMIC_ACCOUNT')
   equity=cash+sum((q*F(a['close_prices'][s][decision]) for s,q in shares.items() if q),F(0));plan=plans[decision]
   expected=deepcopy(plan['search_arguments']);expected.pop('quote_as_of');basis=expected.pop('price_basis');expected['entered_cash']=str(equity)
   require(binding['search_arguments']==expected and binding['source_hashes']==plan['source_hashes'] and binding['decision_date']==decision,'TRUE_CAPITAL_SOURCE_BINDING')
   quotes={q['security_id']:dict(price=str(F(q['price'])),as_of=q['as_of'],price_basis=q['price_basis'],source_references=q['source_references']) for q in plan['valuation_quotes']}
   require(binding['valuation_quotes']==quotes and all(q['price_basis']==basis for q in quotes.values()),'VALUATION_QUOTES')
   owner=parent['records'][decision]['owner'] if parent and decision in parent['records'] else contract['source_hashes'];require(record['research_source_hashes']==owner,'RESEARCH_OWNER_PINS')
   w=windows[decision];td=w['training_dates'];require(len(td)==253 and td==sorted(set(td)) and td[-1]==decision,'TRAINING_253');by={c['security_id']:c for c in w['candidates'] if c.get('security_id')};returns={}
   for sid in expected['prices']:
    values=list(map(F,by[sid]['training_close']));require(len(values)==253 and all(v>0 for v in values),'TRAINING_POSITIVE');returns[sid]=dict(zip(td[1:],[b/a0-1 for a0,b in zip(values,values[1:])]))
   reference=dict(zip(td[1:],[qprices[b]/qprices[a0]-1 for a0,b in zip(td,td[1:])]))
   _,selection_checks[decision]=review_selection(selected,record['sidecar'],returns,reference,owner)
   gate=runner.base.action_gate(window=contract['window'],arguments=record['arguments'],selected=selected,until=ends[decision],active=day,document=document,prices=prices,review=review,legacy=legacy,proof=proof)
   require(gate==saved['gate'] and gate['admitted'],'EXACT_EXPOSURE_GATE_RECHECK')
   baseline=selected['target_quantities'];require(len([q for q in baseline.values() if q])<=10,'MAX10_TARGET');peaks={};exited=set()
  else:
   for e in a['actions']:
    if e['date']!=decision:continue
    s=e['security_id']
    if e['type']=='merger':baseline.pop(s,None);peaks.pop(s,None);exited.discard(s)
    elif s in baseline:
     ratio=F(e['new_shares'])/F(e['old_shares']);n=e.get('new_security_id',s);quantity=baseline.pop(s)*ratio;require(quantity.denominator==1,'RISK_FRACTIONAL');baseline[n]=int(quantity)
     if s in peaks:peaks[n]=peaks.pop(s)/ratio
     if s in exited:exited.remove(s);exited.add(n)
  require(provider['monthly_ceiling']==baseline,'MONTHLY_CEILING')
  for s in baseline:
   price=F(a['close_prices'][s][decision]);peaks[s]=max(peaks.get(s,price),price)
   if price*5<=peaks[s]*4:exited.add(s)
  target={s:0 if s in exited else q for s,q in baseline.items()};require(provider['target_shares']==target,'ORIGINAL20_EXIT_LOCK')
  if baseline:
   state=provider['risk_overlay']['state'];require({s:F(v) for s,v in state['peaks'].items()}==peaks and set(state['exited'])==exited,'RISK_STATE')
  wanted=sorted((s,'BUY' if target.get(s,0)>shares.get(s,0) else 'SELL',abs(target.get(s,0)-shares.get(s,0))) for s in set(target)|set(shares) if target.get(s,0)!=shares.get(s,0));orders=deepcopy(provider['orders']);require(sorted((o['security_id'],o['side'],o['quantity']) for o in orders)==wanted,'TARGET_ORDERS')
  for o in orders:
   require(o['id'] not in order_ids,'DUPLICATE_ORDER_ID');order_ids.add(o['id']);require(o['decision_date']==decision and o['active_date']==day and F(o['decision_mark'])==F(a['close_prices'][o['security_id']][decision]),'NEXT_OPEN_MARK')
  for key,e in events.items():
   if e['ex_date']==day:accrued[key]=shares.get(e['security_id'],0)*F(e['amount_per_share'])*(1-F(e['withholding_rate']))
  for e in a['actions']:
   if e['date']!=day:continue
   s=e['security_id'];kind=e['type']
   if kind=='merger':
    if shares.get(s,0):claims[e['event_id']]=dict(amount=shares[s]*F(e['share_cash']),due=None)
    shares[s]=0;orders=[o for o in orders if o['security_id']!=s];terminated.add(s)
   else:
    require(kind in ('split','split_identity'),'UNSUPPORTED_ACTION');n=e.get('new_security_id',s);ratio=F(e['new_shares'])/F(e['old_shares']);q=shares.get(s,0)*ratio;require(q.denominator==1,'FRACTIONAL_HOLDING')
    if n!=s:
     require(n not in terminated and not shares.get(n,0) and not any(o['security_id']==n for o in orders),'SUCCESSOR_CONFLICT');terminated.add(s)
    if shares.get(s,0) or any(o['security_id']==s for o in orders) or n!=s:shares[s]=0 if n!=s else int(q);shares[n]=int(q)
    for o in orders:
     if o['security_id']==s:q=o['quantity']*ratio;require(q.denominator==1,'FRACTIONAL_ORDER');o['quantity']=int(q);o['security_id']=n
  for o in sorted((o for o in orders if o['side']=='SELL'),key=lambda o:o['id']):
   s=o['security_id'];q=o['quantity'];require(q<=shares.get(s,0),'OVERSELL');cash+=q*F(bars[s][day]['open'])*F(1999,2000);shares[s]-=q;fills.append((day,o['id'],s,'SELL',q,F(bars[s][day]['open'])*F(1999,2000),F(0),cash))
  buys=sorted((o for o in orders if o['side']=='BUY'),key=lambda o:o['id']);cost=sum((o['quantity']*F(bars[o['security_id']][day]['open'])*F(2001,2000) for o in buys),F(0));scale=min(F(1),cash/cost) if cost else F(0)
  for o in buys:
   s=o['security_id'];q=int(o['quantity']*scale);cash-=q*F(bars[s][day]['open'])*F(2001,2000);shares[s]=shares.get(s,0)+q
   if q:fills.append((day,o['id'],s,'BUY',q,F(bars[s][day]['open'])*F(2001,2000),F(0),cash))
  for key,value in accrued.items():
   due=events[key]['payment_date']
   if key not in paid and due is not None and due<=day:cash+=value;paid[key]=day
  pending=sum((v for k,v in accrued.items() if k not in paid),F(0));merger=sum((v['amount'] for v in claims.values()),F(0));stock=sum((q*F(bars[s][day]['close']) for s,q in shares.items() if q),F(0));equity=cash+stock+pending+merger
  require(cash>=0 and F(row['cash'])==cash and row['shares']==shares,'DAILY_CASH_SHARES:'+day);require(F(row['dividend_receivable'])==pending and F(row['receivable'])==merger and F(row['stock_value'])==stock and F(row['equity'])==equity,'DAILY_EQUITY_RIGHTS:'+day)
  require(not row['distribution_rights'] and not row['merger_entitlements'] and F(row['external_flow'])==0,'UNEXPECTED_RIGHTS_FLOW');peak=max(peak,equity);dd=max(dd,1-equity/peak)
 require(selection_count==months and set(selection_checks)==set(plans),'ALL_MONTHLY_SELECTIONS')
 actual_fills=[(x['date'],x['id'],x['security_id'],x['side'],x['quantity'],F(x['price']),F(x['fee']),F(x['cash_after'])) for x in book['order_log'] if x['event']=='ASSUMED_NEXT_OPEN_FILLED'];require(actual_fills==fills,'EXACT_FILL_LOG')
 require(F(book['cash'])==cash and book['shares']==shares and F(book['fees'])==0,'TERMINAL_CASH_SHARES');require(F(book['total_return'])==equity/F(20000)-1 and F(book['drawdown']['maximum_close_drawdown'])==dd,'TERMINAL_RETURN_DRAWDOWN')
 dl=book['dividend_ledger'];require(set(dl['events'])==set(accrued),'DIVIDEND_EVENT_SET')
 for key,value in accrued.items():require(dl['events'][key]['event']==events[key] and F(dl['events'][key]['net'])==value,'DIVIDEND_RIGHTS')
 require(len(dl['payments'])==len({p['event_id'] for p in dl['payments'].values()})==len(paid),'DUPLICATE_PAYMENT');require({p['event_id']:p['session_date'] for p in dl['payments'].values()}==paid and F(dl['receivable'])==pending and F(dl['paid_cash'])==sum((accrued[k] for k in paid),F(0)),'PAYMENTS_AND_UNPAID')
 return dict(status='INDEPENDENT_CAP20_CONDITIONAL_ACCOUNT_ARITHMETIC_PASS' if contract.get('conditional_assumption_dependency') else 'INDEPENDENT_CAP20_ACCOUNT_PASS',conditional_assumptions=contract.get('conditional_assumption_dependencies',[contract['conditional_assumption_dependency']] if contract.get('conditional_assumption_dependency') else []),production_eligible=False,assumption_exposure=[assumption_exposure(book,document,dict(conditional_assumption_dependency=d)) for d in contract.get('conditional_assumption_dependencies',[contract['conditional_assumption_dependency']] if contract.get('conditional_assumption_dependency') else [])],window=contract['window'],sessions=count,months_checked=months,trades_checked=len(fills),selection_checks=selection_checks,final_equity=str(equity),maximum_drawdown=str(dd),merger_unpaid_claims=len(claims),scope='Independent exact accounting and retained candidate score/risk/cap20/owner checks. Original observed all-candidate dominance cannot be independently proven without full observation stream. No candidate apply or search.',economic_replays=0)

def assumption_exposure(book,document,contract):
 dependency=contract.get('conditional_assumption_dependency')
 if not dependency:return None
 require(dependency['absence_proven'] is False and dependency['security_id']=='research:security:alxn' and (dependency['start_exclusive'],dependency['end_inclusive']) in [('2021-04-30','2021-05-28'),('2021-05-28','2021-06-01')],'EXACT_CONDITIONAL_SCOPE')
 if dependency['end_inclusive']=='2021-06-01':
  from docs.candidates.cap20_alxn_june_exit_assumption_20261105 import assert_exit
  assert_exit(book['daily_ledger'])
 sid=dependency['security_id'];start=dependency['start_exclusive'];end=dependency['end_inclusive'];rows=[r for r in book['daily_ledger'] if start<r['date']<=end];before=next(r for r in book['daily_ledger'] if r['date']==start);bars=document['ohlc'][sid];opening=before['shares'].get(sid,0);initial_value=opening*F(bars[start]['close']);last=rows[-1];terminal_value=last['shares'].get(sid,0)*F(bars[end]['close']);fills=[r for r in book['order_log'] if r['event']=='ASSUMED_NEXT_OPEN_FILLED' and r['security_id']==sid and start<r['date']<=end]
 net=sum(((1 if r['side']=='SELL' else -1)*r['quantity']*F(r['price'])-F(r['fee']) for r in fills),F(0))
 return dict(security_id=sid,start_exclusive=start,end_inclusive=end,opening_shares=opening,ending_shares=last['shares'].get(sid,0),opening_market_value=str(initial_value),ending_market_value=str(terminal_value),net_trade_cash=str(net),price_and_trade_contribution=str(terminal_value+net-initial_value),sessions=[dict(date=r['date'],shares=r['shares'].get(sid,0),market_value=str(r['shares'].get(sid,0)*F(bars[r['date']]['close']))) for r in rows],fills=fills,interpretation='Actual accounting path conditional on no unobserved ALXN action in the declared interval. Not an error bound, not proof that dividend/split rights did not occur, and not production admission.')

def run(output):
 directory=ROOT/output
 try:report=audit(directory);error=None
 except Exception as exc:report=dict(status='FAILED',reason=repr(exc));error=exc
 paths=[Path(__file__),Path(prior.__file__),ROOT/'scripts/research/review_momentum_account_20261105.py',ROOT/'backtest/capped_frontier_independent_review.py',ROOT/'backtest/research_exact_fraction_json.py']+[directory/n for n in ('book.json','contract.json','summary.json','execution_inputs.json','additional_execution_evidence.json')]+list(directory.glob('*.selection.json'))+list(directory.glob('*.decision.json'))
 report['source_hashes']={p.relative_to(ROOT).as_posix():digest(p) for p in paths if p.exists()};report['book_sha256']=digest(directory/'book.json');(directory/'independent_review.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps({k:v for k,v in report.items() if k not in ('source_hashes','selection_checks')}))
 if error:raise error
 return report
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);run(parser.parse_args().output)
