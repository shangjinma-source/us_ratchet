"""Two fixed staged-stop daily proxies, isolated from frozen v6 engine."""
import argparse,json,time
from pathlib import Path
from hashlib import sha256
from copy import deepcopy
from backtest.research_exact_fraction_json import loads,dumps
from scripts.research import run_pullback_account_20261105 as base
from docs.candidates.pullback_staged_engine_20261105 import run_account
from docs.candidates.pullback_volume_filter_20261105 import filter_volume_signals
ROOT=base.ROOT
def run(output,volume=False):
 out=ROOT/output;base.need(out.resolve().is_relative_to(ROOT/'tmp'),'TMP_ONLY');out.mkdir(parents=True,exist_ok=False);parent='tmp/pullback_account_20261105/early_price_v7';contract=loads((ROOT/parent/'contract.json').read_bytes());base.original.check(contract['source_hashes']);pins=dict(contract['source_hashes'])
 def read(path):
  raw=(ROOT/path).read_bytes();pins[path]=sha256(raw).hexdigest();return loads(raw)
 source=read(parent+'/execution_inputs.json');document=source['document'];review=source['review'];signals=read(parent+'/signals.json');read(parent+'/contract.json')
 from docs.candidates.pullback_staged_early_supplement_20261105 import append_review as append_early
 for name,method in [('early_supplement',append_early)]:
  extra=method(document,review);pins.update(extra['source_hashes']);base.save(out/('additional_'+name+'.json'),extra)
 for name in ['docs/candidates/pullback_staged_early_supplement_20261105.py',Path(__file__).relative_to(ROOT).as_posix(),'docs/candidates/pullback_staged_engine_20261105.py','docs/candidates/pullback_staged_contract_20261105.md','docs/candidates/pullback_volume_filter_20261105.py']:pins[name]=sha256((ROOT/name).read_bytes()).hexdigest()
 if volume:
  sp='tmp/pullback_account_20261105/early_price_v5/signals.json';ip=parent+'/execution_inputs.json';rp='tmp/pullback_account_20261105/signal_volume_pairs_review.json';vp='tmp/pullback_volume_inventory_20261105_v3_final/early.json';expected={p:sha256((ROOT/p).read_bytes()).hexdigest() for p in (sp,ip,rp,vp)};base.need(read(sp)==signals,'PARENT_SIGNALS_IDENTICAL')
  signals,volume_audit=filter_volume_signals(root=ROOT,window='early',signals_path=sp,execution_inputs_path=ip,review_path=rp,expected_hashes=expected);pins.update(volume_audit['source_hashes']);base.save(out/'volume_audit.json',volume_audit)
 freeze=base.original.read('research_contracts/momentum_account_execution_20261105/freeze.json');_,prices,_,legacy,proof=base.original.inventory.inputs('2021_2023',base.original.read(freeze['inventory_base_freeze']));split=base.original.FixedSplitAdmission();cache={}
 def gate(previous,day,shares,entries):
  target={**shares,**{e['security_id']:shares.get(e['security_id'],0)+e['quantity'] for e in entries}};key=(previous,day,tuple(sorted(shares.items())),tuple(sorted(target.items())))
  if key not in cache:
   args=dict(decision_date=previous,account_state=dict(shares=shares));selected=dict(target_quantities=target)
   value=base.original.inventory.exposed_action_blockers(args,selected,day,prices,review,day,document['dividend_events']);value=split.admit(value,document,'2021_2023')
   if 'research:security:sgen' in value['exposed']:value=base.original.sgen_admit(gate=value,document=document,arguments=args,selected=selected,active=day)
   cache[key]=value
   if not value['admitted']:base.save(out/('failure_gate_'+day+'.json'),value)
  return deepcopy(cache[key])
 base.save(out/'contract.json',dict(window='2021_2023',source_hashes=pins,initial_cash='20000',variant='staged_3r',volume_contraction=volume,parent=parent,scope='FIXED_DAILY_PROXY_NOT_MINUTE_STRATEGY'))
 base.save(out/'signals.json',signals);base.save(out/'execution_inputs.json',source)
 book=run_account(session_dates=document['assembled']['session_dates'],ohlc=document['ohlc'],signals=signals,actions=document['assembled']['actions'],dividend_events=document['dividend_events'],gate=gate,variant='staged_3r',settlement_delay=0)
 base.save(out/'book.json',book);base.original.check(pins);summary={k:book[k] for k in ('status','reason','total_return','maximum_drawdown')};summary.update(sessions=len(book['daily_ledger']),fills=len(book['order_log']));base.save(out/'summary.json',summary);print(summary)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--volume',action='store_true');a=p.parse_args();run(a.output,a.volume)
