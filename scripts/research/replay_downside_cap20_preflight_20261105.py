"""Accounting-only first-month replay; hard refusal of any new search."""
import argparse,gzip,importlib.util,json,time
from collections import Counter
from copy import deepcopy
from datetime import datetime,timezone
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
from backtest.research_exact_fraction_json import loads
from scripts.research import run_momentum_account_20261105 as base
from docs.candidates.downside_cap20_selection_20261105 import apply_downside_selection
from docs.candidates.downside_resume_chain_20261105 import append_ordinary_artifact
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
from scripts.run_old_continuous_probe_v1 import validate_selection_binding
ROOT=base.ROOT
PARENT='tmp/downside_cap20_preflight_20261105_v2'
PRIOR_FAILED='tmp/downside_cap20_preflight_20261105_v1/summary.json'
ARTIFACT='tmp/kdp_20240104_dividend_evidence_20261105/supplement.json'
ARTIFACT_SHA='0c96e5ee35a6877458dfc77a71c7aabfd2c6a520fd9141a190dd02e3a8247c78'
def normalize_observations(document, artifact):
 normalized=deepcopy(artifact);receipt=[]
 canonical=lambda rows:Counter(json.dumps(r,sort_keys=True,separators=(',',':')) for r in rows)
 for row in normalized['review_rows']:
  ticker=document['prepared_input_candidate']['metadata'][row['security_id']]['ticker']
  actual=[e for e in document['provider_event_inventory'] if e['ticker']==ticker and e['kind']=='dividends' and e['date']==row['ex_date']]
  base.need(actual and canonical(actual)==canonical(row['observed_provider_events']),'EXACT_PROVIDER_MULTISET_REQUIRED')
  receipt.append(dict(security_id=row['security_id'],ex_date=row['ex_date'],original=row['observed_provider_events'],normalized=deepcopy(actual),operation='ORDER_ONLY_EXACT_MULTISET'))
  row['observed_provider_events']=deepcopy(actual)
 return normalized,receipt

def run(output):
 start=time.monotonic();out=(ROOT/output).resolve();base.need(out.is_relative_to(ROOT/'tmp'),'TMP_ONLY');base.need(not out.exists(),'NEW_OUTPUT_ONLY');pins={};parent_files={}
 def load(path):
  raw=(ROOT/path).read_bytes();parent_files[path]=sha256(raw).hexdigest();return loads(raw)
 contract=load(PARENT+'/contract.json');base.check(contract['source_hashes']);pins.update(contract['source_hashes']);summary=load(PARENT+'/summary.json');prior=load(PRIOR_FAILED);record=load(PARENT+'/selection.json');parent_book=load(PARENT+'/book.json');parent_decision=load(PARENT+'/decision.json');inputs=load(PARENT+'/execution_inputs.json')
 base.need(summary['status']=='PREFLIGHT_FAILED' and parent_book['status']=='BLOCKED' and not parent_book['daily_ledger'],'EXACT_FAILED_EMPTY_PREFIX_PARENT')
 base.need(prior['status']=='PREFLIGHT_FAILED' and 'selection.json' not in [p.name for p in (ROOT/Path(PRIOR_FAILED).parent).glob('selection.json')],'PRIOR_FAILURE_MUST_HAVE_NO_SELECTION')
 inherited=summary['elapsed_seconds']+prior['elapsed_seconds'];base.need(inherited<10800,'BUDGET_EXHAUSTED');cached=record['raw_selection'];sidecar=record['sidecar'];base.need(sidecar['complete'] and sidecar['single_target_cap']=='1/5','COMPLETE_CAP20_PARENT')
 document=inputs['document'];review=inputs['review'];raw=(ROOT/ARTIFACT).read_bytes();base.need(sha256(raw).hexdigest()==ARTIFACT_SHA,'KDP_FIXED_PIN');artifact=json.loads(raw);base.check(artifact['source_hashes']);normalized,normalization=normalize_observations(document,artifact);append_ordinary_artifact(document,review,normalized);pins.update(artifact['source_hashes']);pins[ARTIFACT]=ARTIFACT_SHA
 freeze=base.read('research_contracts/momentum_account_execution_20261105/freeze.json');_,prices,_,legacy,proof=base.inventory.inputs('2024_2026',base.read(freeze['inventory_base_freeze']))
 training_path='tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json';base.need(base.digest(training_path)==contract['source_hashes'][training_path],'PARENT_TRAINING_PIN');training=base.read(training_path);item=next(o.get('window',o) for o in training['windows'] if o.get('window',o).get('decision_cutoff',o.get('window',o).get('decision_date'))=='2023-12-29');dates=item['training_dates'];candidates={c['security_id']:c for c in item['candidates'] if c.get('security_id')};returns={}
 for sid in record['arguments']['search_arguments']['prices']:
  values=list(map(F,candidates[sid]['training_close']));base.need(len(values)==253 and dates[-1]=='2023-12-29','TRAINING_WINDOW');returns[sid]=dict(zip(dates[1:],[b/a-1 for a,b in zip(values,values[1:])]))
 qprices={}
 for name in ('tmp/qqq_month_end_warmup_20261026_v1/QQQ.response.bin','data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin'):
  raw=(ROOT/name).read_bytes();base.need(sha256(raw).hexdigest()==contract['source_hashes'][name],'QQQ_PIN');data=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)['chart']['result'][0]
  for stamp,value in zip(data['timestamp'],data['indicators']['quote'][0]['close']):
   if value is None:continue
   day=datetime.fromtimestamp(stamp,timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat();v=F(str(value));base.need(day not in qprices or qprices[day]==v,'QQQ_OVERLAP');qprices[day]=v
 reference=dict(zip(dates[1:],[qprices[b]/qprices[a]-1 for a,b in zip(dates,dates[1:])]))
 own=Path(__file__).relative_to(ROOT).as_posix();pins[own]=base.digest(own);pins.update(parent_files);base.check(pins);out.mkdir(parents=True);base.save(out/'contract.json',dict(scope='ACCOUNTING_ONLY_PREFLIGHT_REPLAY_NO_SEARCH',window='2024_2026',source_hashes=pins,selection_research_source_hashes=contract['source_hashes'],parent_file_hashes=parent_files,inherited_seconds=inherited,inherited_searches=1,cap='1/5',initial_cash='20000'))
 base.save(out/'execution_inputs.json',inputs);base.save(out/'selection.json',record);base.save(out/'additional_execution_evidence.json',artifact);base.save(out/'normalization_receipt.json',normalization)
 def guard():base.need(inherited+time.monotonic()-start<600 and inherited+time.monotonic()-start<10800,'CUMULATIVE_TIME_LIMIT')
 called=[]
 def select(**arguments):
  guard();base.need(not called and arguments==record['arguments'],'STRICT_PARENT_ARGUMENTS_OR_REPEAT');validate_selection_binding(cached,arguments);called.append(arguments['decision_date']);return deepcopy(cached)
 def rerank(raw):
  guard();base.need(raw==cached,'RAW_PARENT_CHANGED');selected=apply_downside_selection(raw=raw,sidecar=sidecar,stock_returns=returns,qqq_reference=reference,research_source_hashes=contract['source_hashes']);base.need(selected==parent_decision['selected'],'ORIGINAL_SELECTION_CHANGED')
  gate=base.action_gate(window='2024_2026',arguments=record['arguments'],selected=selected,until='2024-01-31',active='2024-01-02',document=document,prices=prices,review=review,legacy=legacy,proof=proof);base.save(out/'decision.json',dict(selected=selected,gate=gate));base.need(gate['admitted'],'ACCOUNTING_GATE_FAILED');return selected
 spec=importlib.util.spec_from_file_location('cap20_replay_private_kernel',ROOT/'docs/candidates/qqq_risk_budget_account_runner.py');kernel=importlib.util.module_from_spec(spec);spec.loader.exec_module(kernel);kernel.decide_continuous_guided_for_account=select;kernel.rerank=rerank
 try:
  guard()
  book=kernel.run_frontier_capped_next_open(assembled=document['assembled'],ohlc=document['ohlc'],initial_cash='20000',fee_bps='0',slippage_bps='5',risk=MonthlyExitCoreResearchAdapter(document['assembled']['actions']),max_new_searches=1,dividend_events=document['dividend_events']);base.save(out/'book.json',book);guard();base.check(pins);base.need(book['status']=='COMPLETE' and len(book['daily_ledger'])==21,'NOT_COMPLETE_21_SESSIONS');result=dict(status=book['status'],reason=book.get('reason'),completed_sessions=len(book['daily_ledger']),required_sessions=21,searches=dict(new=1,reused=0,replayed=len(called)),new_searches_this_run=0,kernel_new_searches_note='One cached callback; zero actual search invocations',elapsed_seconds=inherited+time.monotonic()-start,parent_prefix_rows=0,parent_prefix_claim='EMPTY_ONLY_NOT_21_DAYS',full_window=False)
 except Exception as error:
  result=dict(status='FAILED',reason=repr(error),new_searches_this_run=0,searches=dict(new=1,replayed=len(called)),elapsed_seconds=inherited+time.monotonic()-start);base.save(out/'summary.json',result);raise
 base.save(out/'summary.json',result);print(json.dumps(result))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();run(a.output)
