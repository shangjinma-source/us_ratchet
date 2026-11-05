"""Fixed cap20 full-account runner. Preparation is not authorization to execute."""
import argparse,gzip,importlib.util,json,time,os
from copy import deepcopy
from datetime import datetime,timezone
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
from backtest.research_exact_fraction_json import loads
from scripts.research import run_momentum_account_20261105 as base
from scripts.research.replay_downside_cap20_preflight_20261105 import normalize_observations
from docs.candidates.downside_cap20_selection_20261105 import decide_observed_for_account,apply_downside_selection
from docs.candidates.downside_absence_artifact_20261105 import append_execution_artifact
from docs.candidates.downside_resume_chain_20261105 import append_ordinary_artifact
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
from scripts.run_old_continuous_probe_v1 import validate_selection_binding
ROOT=base.ROOT
SCHEMA='FIXED_CAP20_ACCOUNT_EXECUTION_V1'
SELF='scripts/research/run_downside_cap20_account_20261105.py'
CORE=['docs/candidates/downside_cap20_selection_20261105.py','backtest/downside_cap20_observer_20261105.py','backtest/concentration_cap20_research_20261105.py',SELF,'scripts/research/replay_downside_cap20_preflight_20261105.py','docs/candidates/downside_absence_artifact_20261105.py','docs/candidates/downside_resume_chain_20261105.py']
def exact(path):return loads((ROOT/path).read_bytes())
def merge_pins(pins,extra):
 base.check(extra)
 for k,v in extra.items():base.need(k not in pins or pins[k]==v,'CONFLICTING_PIN:'+k);pins[k]=v

def append_pairs(document,review,artifact):
 """Deduplicate only identical nominal financial terms; retain both source closures."""
 if artifact.get('schema')=='BOUNDED_PROVIDER_ABSENCE_V1':
  key=lambda r:(r.get('security_id'),r.get('start_exclusive'),r.get('end_inclusive'),r.get('status'))
  keys={key(r) for r in artifact['review_rows']};existing=[r for r in review['rows'] if key(r) in keys]
  if not existing:append_execution_artifact(document,review,artifact);return {'kind':'BOUNDED_ABSENCE'}
  base.need(len(existing)==len(keys),'DUPLICATE_ABSENCE_ROWS')
  isolated=deepcopy(review);isolated['rows']=[r for r in isolated['rows'] if key(r) not in keys];append_execution_artifact(document,isolated,artifact)
  derived=[r for r in isolated['rows'] if key(r) in keys];base.need(sorted(existing,key=key)==sorted(derived,key=key),'EXISTING_ABSENCE_NOT_EXACT_INDEPENDENT_DERIVATION')
  return {'kind':'EXISTING_ABSENCE_REVALIDATED_RAW_REQUEST'}
 normalized,receipt=normalize_observations(document,artifact);added=[];matched=[]
 for row,event in zip(normalized['review_rows'],normalized['dividend_events'],strict=True):
  old=[e for e in document['dividend_events'] if e['security_id']==event['security_id'] and e['ex_date']==event['ex_date']]
  base.need(len(old)<=1,'EXISTING_DUPLICATE_DIVIDEND')
  if old:
   for field in ('security_id','ex_date','payment_date','currency'):base.need(old[0][field]==event[field],'DIVIDEND_CONFLICT:'+field)
   for field in ('amount_per_share','withholding_rate'):base.need(F(old[0][field])==F(event[field]),'DIVIDEND_CONFLICT:'+field)
   base.need(any(r.get('security_id')==event['security_id'] and r.get('ex_date')==event['ex_date'] and r.get('payment_date')==event['payment_date'] and F(r.get('amount_per_share','-1'))==F(event['amount_per_share']) for r in review['rows']),'EXISTING_DIVIDEND_HAS_NO_PAIRED_REVIEW')
   matched.append(event['event_id'])
  else:
   part=deepcopy(normalized);part['review_rows']=[row];part['dividend_events']=[event];append_ordinary_artifact(document,review,part);added.append(event['event_id'])
 return dict(added=added,existing_exact=matched,normalization=receipt)

def prepare(window,extra_artifacts):
 freeze=base.read('research_contracts/momentum_account_execution_20261105/freeze.json');old=base.read('research_contracts/downside_max10_20261105/freeze.json');pins={};merge_pins(pins,freeze['source_hashes']);merge_pins(pins,old['source_hashes']);base.inventory.PINS.clear()
 document,prices,review,legacy,proof=base.inventory.inputs(window,base.read(freeze['inventory_base_freeze']));merge_pins(pins,base.inventory.PINS)
 document,review=base.prepare_actions(window=window,document=document,prices=prices,review=review,pins=pins,freeze=freeze);receipts=[]
 for name in extra_artifacts:
  artifact=base.read(name);merge_pins(pins,artifact['source_hashes']);pins[name]=base.digest(name);receipts.append(dict(path=name,audit=append_pairs(document,review,artifact)))
 dates=document['assembled']['session_dates'];document['dividend_events']=[e for e in document['dividend_events'] if dates[0]<e['ex_date']<=dates[-1]]
 train='tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json' if window=='2024_2026' else 'tmp/qqq_20201231_anchor_20261025/recent_training_windows_v1.json'
 training=base.read(train);merge_pins(pins,training['source_hashes']);windows={}
 for outer in training['windows']:
  item=outer.get('window',outer);windows[item.get('decision_cutoff',item.get('decision_date'))]=item
 qprices={};quotes=['tmp/qqq_month_end_warmup_20261026_v1/QQQ.response.bin','data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin']
 manifest=base.read('research_contracts/research_archive_20261026/trend_fixed_candidate_v1_manifest.json')['base_file_dependencies']
 for name in [train,*quotes]:base.need(base.digest(name)==manifest[name],'FROZEN_TRAINING:'+name);pins[name]=manifest[name]
 for name in quotes:
  raw=(ROOT/name).read_bytes();data=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)['chart']['result'][0]
  for stamp,value in zip(data['timestamp'],data['indicators']['quote'][0]['close']):
   if value is None:continue
   day=datetime.fromtimestamp(stamp,timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat();v=F(str(value));base.need(day not in qprices or qprices[day]==v,'QQQ_OVERLAP');qprices[day]=v
 for name in CORE:pins[name]=base.digest(name)
 return document,prices,review,legacy,proof,pins,windows,qprices,receipts

def load_parent(path):
 if not path:return None
 path=Path(path);contract=exact(path/'contract.json');summary=exact(path/'summary.json');book=exact(path/'book.json');base.check(contract['source_hashes'])
 base.need(summary['status'] in ('COMPLETE','BLOCKED') and len(book['daily_ledger'])==summary['completed_sessions'],'PARENT_LEDGER_STATUS')
 hashes={};records={}
 def bind(name):hashes[str(name)]=base.digest(name)
 for name in ('contract.json','summary.json','book.json'):bind(path/name)
 if contract.get('scope')=='ACCOUNTING_ONLY_PREFLIGHT_REPLAY_NO_SEARCH':
  record=exact(path/'selection.json');bind(path/'selection.json');day=record['arguments']['decision_date'];records[day]=dict(record=record,owner=contract['selection_research_source_hashes']);base.check(records[day]['owner']);summary['monthly_elapsed_seconds']={day:summary['elapsed_seconds']}
 else:
  base.need(contract.get('schema')==SCHEMA,'PARENT_SCHEMA')
  for name in sorted((ROOT/path).glob('*.selection.json')):
   relative=name.relative_to(ROOT);record=exact(relative);bind(relative);records[record['arguments']['decision_date']]=dict(record=record,owner=record['research_source_hashes']);base.check(record['research_source_hashes'])
 base.need(summary['searches']['new']==len(records),'NO_RETRY_OF_UNSAVED_SEARCH')
 return dict(path=str(path),contract=contract,summary=summary,book=book,records=records,hashes=hashes)

def run(*,window,output,freeze_path,parent_path=None):
 started=time.monotonic();freeze=base.read(freeze_path);base.need(freeze['schema']==SCHEMA and freeze['window']==window and freeze['parent_output']==parent_path,'EXECUTION_FREEZE');base.need(freeze['seconds_per_window']==10800 and freeze['seconds_per_month']==600,'FROZEN_BUDGET');base.check(freeze['source_hashes'])
 document,prices,review,legacy,proof,pins,windows,qprices,receipts=prepare(window,freeze['additional_execution_artifacts']);base.need(pins==freeze['source_hashes'],'EXACT_EXECUTION_SOURCE_CLOSURE');parent=load_parent(parent_path);base.need((parent['hashes'] if parent else {})==freeze['parent_file_hashes'],'FROZEN_PARENT_FILES')
 inherited=parent['summary']['elapsed_seconds'] if parent else 0;budget=dict(new=parent['summary']['searches']['new'] if parent else 0,replayed=0);months=31 if window=='2024_2026' else 36;out=(ROOT/output).resolve();base.need(out.is_relative_to(ROOT/'tmp'),'TMP_OUTPUT');out.mkdir(parents=True,exist_ok=False)
 dates=document['assembled']['session_dates'];plans=document['assembled']['monthly_inputs'];base.need(len(plans)==months,'MONTH_COUNT');ends={p['decision_date']:(plans[i+1]['decision_date'] if i+1<months else dates[-1]) for i,p in enumerate(plans)}
 contract=dict(schema=SCHEMA,window=window,source_hashes=pins,parent_output=parent_path,parent_file_hashes=parent['hashes'] if parent else {},inherited_seconds=inherited,inherited_searches=budget['new'],seconds_per_window=10800,seconds_per_month=600,monthly_budget_scope='Cumulative monthly selection and rerank verification; first month conservatively inherits entire preflight/replay',window_budget_scope='Includes preparation, action gates, daily accounting and all parent elapsed',cap='1/5',max_holdings=10,pid=os.getpid())
 base.save(out/'contract.json',contract);base.save(out/'execution_inputs.json',dict(document=document,review=review));base.save(out/'additional_execution_evidence.json',receipts)
 contexts={};prefix_done=[not parent or not parent['book']['daily_ledger']];prefix=parent['book']['daily_ledger'] if parent else [];monthly_elapsed={};checked=[0]
 def guard():base.need(inherited+time.monotonic()-started<10800,'CUMULATIVE_WINDOW_TIME')
 def verify_progress(rows):
  for i in range(checked[0],min(len(rows),len(prefix))):base.need(rows[i]==prefix[i],'PARENT_LEDGER_PREFIX_CHANGED:'+str(i))
  checked[0]=min(len(rows),len(prefix));prefix_done[0]=len(rows)>=len(prefix)
 def select(**arguments):
  guard();day=arguments['decision_date'];base.need(day not in contexts,'DUPLICATE_SELECTION_CALLBACK');month_start=time.monotonic();saved=parent['records'].get(day) if parent else None
  def month_guard():
   guard();used=(parent['summary'].get('monthly_elapsed_seconds',{}).get(day,0) if saved else 0);base.need(used+time.monotonic()-month_start<600,'CUMULATIVE_MONTH_TIME')
  item=windows[day];td=item['training_dates'];base.need(len(td)==253 and td==sorted(set(td)) and td[-1]==day,'TRAINING_DATES');by={c['security_id']:c for c in item['candidates'] if c.get('security_id')};returns={}
  for sid in arguments['search_arguments']['prices']:
   values=list(map(F,by[sid]['training_close']));base.need(len(values)==253 and all(v>0 for v in values),'TRAINING_PRICES');returns[sid]=dict(zip(td[1:],[b/a-1 for a,b in zip(values,values[1:])]))
  reference=dict(zip(td[1:],[qprices[b]/qprices[a]-1 for a,b in zip(td,td[1:])]))
  if saved:
   record=deepcopy(saved['record']);base.need(arguments==record['arguments'],'PARENT_ARGUMENTS_CHANGED');raw=record['raw_selection'];sidecar=record['sidecar'];owner=saved['owner'];budget['replayed']+=1
  else:
   base.need(prefix_done[0],'PREFIX_BEFORE_NEW_SEARCH');base.need(budget['new']<months,'CUMULATIVE_SEARCH_LIMIT');budget['new']+=1;base.save(out/'search_budget.json',budget);owner=pins
   raw,sidecar=decide_observed_for_account(stock_returns=returns,qqq_reference=reference,research_source_hashes=owner,max_holdings=10,guard=month_guard,**arguments)
  validate_selection_binding(raw,arguments);month_guard();contexts[day]=dict(arguments=deepcopy(arguments),returns=returns,reference=reference,sidecar=sidecar,owner=owner);monthly_elapsed[day]=(parent['summary'].get('monthly_elapsed_seconds',{}).get(day,0) if saved else 0)+time.monotonic()-month_start
  base.save(out/(day+'.selection.json'),dict(arguments=arguments,raw_selection=raw,sidecar=sidecar,research_source_hashes=owner));return raw
 def rerank(raw):
  guard();rerank_start=time.monotonic();day=raw['decision_date'];c=contexts[day];selected=apply_downside_selection(raw=raw,sidecar=c['sidecar'],stock_returns=c['returns'],qqq_reference=c['reference'],research_source_hashes=c['owner']);gate=base.action_gate(window=window,arguments=c['arguments'],selected=selected,until=ends[day],active=dates[dates.index(day)+1],document=document,prices=prices,review=review,legacy=legacy,proof=proof);base.save(out/(day+'.decision.json'),dict(selected=selected,gate=gate));monthly_elapsed[day]+=time.monotonic()-rerank_start;base.need(monthly_elapsed[day]<600,'CUMULATIVE_MONTH_TIME');base.need(gate['admitted'],'ACTUAL_MONTHLY_ACTION_GATE:'+day);return selected
 spec=importlib.util.spec_from_file_location('cap20_full_private_kernel',ROOT/'docs/candidates/qqq_risk_budget_account_runner.py');kernel=importlib.util.module_from_spec(spec);spec.loader.exec_module(kernel);original_book=kernel.run_next_open_book
 def guarded_book(**kwargs):
  provider=kwargs['order_provider']
  def callback(**state):guard();verify_progress(state['state']['daily_ledger']);return provider(**state)
  kwargs['order_provider']=callback;return original_book(**kwargs)
 kernel.decide_continuous_guided_for_account=select;kernel.rerank=rerank;kernel.run_next_open_book=guarded_book
 try:
  guard();book=kernel.run_frontier_capped_next_open(assembled=document['assembled'],ohlc=document['ohlc'],initial_cash='20000',fee_bps='0',slippage_bps='5',risk=MonthlyExitCoreResearchAdapter(document['assembled']['actions']),max_new_searches=months,dividend_events=document['dividend_events']);base.save(out/'book.json',book);verify_progress(book['daily_ledger']);base.need(prefix_done[0],'INCOMPLETE_PARENT_REPLAY');guard();base.check(pins)
  if parent:base.check(parent['hashes'])
  base.need(book['status']!='COMPLETE' or len(book['daily_ledger'])==len(dates)-1,'COMPLETE_SESSION_COUNT')
  result=dict(status=book['status'],reason=book.get('reason'),completed_sessions=len(book['daily_ledger']),required_sessions=len(dates)-1,searches=budget,elapsed_seconds=inherited+time.monotonic()-started,monthly_elapsed_seconds=monthly_elapsed,parent_prefix_rows=len(prefix),independently_reviewed=False)
 except Exception as error:
  base.save(out/'failure.json',dict(status='FAILED',reason=repr(error),searches=budget,elapsed_seconds=inherited+time.monotonic()-started,monthly_elapsed_seconds=monthly_elapsed,no_automatic_retry=True));raise
 base.save(out/'summary.json',result);print(json.dumps(result))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--window',choices=['2021_2023','2024_2026'],required=True);p.add_argument('--output',required=True);p.add_argument('--freeze',required=True);p.add_argument('--parent');a=p.parse_args();run(window=a.window,output=a.output,freeze_path=a.freeze,parent_path=a.parent)
