"""Three-session real provider/risk integration; cached exact decision, zero searches."""
from pathlib import Path
from copy import deepcopy
from hashlib import sha256
from backtest.research_exact_fraction_json import loads
from scripts.research.run_downside_cap20_azn_zero_recovery_20261105 import make_runner,POLICY
from docs.candidates.cap20_azn_zero_recovery_20261105 import OLD,NEW,validate_rights
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
def run():
 r=make_runner();parent=r.ROOT/'tmp/downside_cap20_full_20261105_late_v4';read=lambda name:loads((parent/name).read_bytes());names=[x['path'] for x in read('additional_execution_evidence.json')]+[POLICY];v=r.prepare('2024_2026',names);doc=v[0];record=read('2026-01-30.selection.json');selected=read('2026-01-30.decision.json')['selected'];state=record['arguments']['account_state'];assembled=deepcopy(doc['assembled']);assembled['session_dates']=[d for d in assembled['session_dates'] if '2026-01-30'<=d<='2026-02-04'];assembled['monthly_inputs']=[p for p in assembled['monthly_inputs'] if p['decision_date']=='2026-01-30'];assembled['actions']=[e for e in assembled['actions'] if '2026-01-30'<e['date']<='2026-02-04'];assembled['provider_actions']=deepcopy(assembled['actions'])
 gate=r.base.action_gate(window='2024_2026',arguments=record['arguments'],selected=selected,until='2026-02-27',active='2026-02-02',document=doc,prices=v[1],review=v[2],legacy=v[3],proof=v[4]);r.base.need(gate['admitted'] and len(gate['original_gate_rejection_preserved']['unmapped_events'])==2,'REAL_ACTION_GATE_EXACT_TWO_AZN_BARRIERS')
 spec=r.importlib.util.spec_from_file_location('actual_private_kernel_integration',r.ROOT/'docs/candidates/qqq_risk_budget_account_runner.py');kernel=r.importlib.util.module_from_spec(spec);spec.loader.exec_module(kernel);original_book=kernel.run_next_open_book;calls=[]
 def select(**args):r.base.need(args==record['arguments'],'ACTUAL_PARENT_ARGUMENTS_DIFFER');calls.append(args['decision_date']);return deepcopy(record['raw_selection'])
 def rerank(raw):r.base.need(raw==record['raw_selection'],'RAW_CHANGED');return deepcopy(selected)
 def book(**kwargs):kwargs['initial_shares']=deepcopy(state['shares']);return original_book(**kwargs)
 kernel.decide_continuous_guided_for_account=select;kernel.rerank=rerank;kernel.run_next_open_book=book
 result=kernel.run_frontier_capped_next_open(assembled=assembled,ohlc=doc['ohlc'],initial_cash=state['cash'],fee_bps='0',slippage_bps='5',risk=MonthlyExitCoreResearchAdapter(assembled['actions']),max_new_searches=1,dividend_events=[])
 r.base.need(result['status']=='COMPLETE' and len(result['daily_ledger'])==3 and calls==['2026-01-30'],'REAL_KERNEL_COMPLETE_REUSED');r.base.need(all(x['status']=='READY' for x in result['provider_audit']),'READY_PROVIDER')
 fills=[x for x in result['order_log'] if x['event']=='ASSUMED_NEXT_OPEN_FILLED' and x['security_id'] in (OLD,NEW)];r.base.need([(x['date'],x['security_id'],x['quantity']) for x in fills]==[('2026-02-03',NEW,24)],'EXACT_NEXT_SESSION24_EXIT');r.base.need(any(x['event']=='CANCELLED_ADS_CONVERSION' and x['date']=='2026-02-02' for x in result['order_log']),'OLD_ORDER_CANCELLED')
 validate_rights(result['distribution_rights']);r.base.need(result['daily_ledger'][0]['shares'][NEW]==24 and result['shares'][NEW]==0,'WHOLE_SHARES_EXITED')
 out=r.ROOT/'tmp/cap20_azn_zero_recovery_kernel_integration_20261105';out.mkdir(exist_ok=True);r.base.save(out/'book.json',result);pins=dict(v[5]);pins[Path(__file__).relative_to(r.ROOT).as_posix()]=sha256(Path(__file__).read_bytes()).hexdigest();pins.update({(parent/n).relative_to(r.ROOT).as_posix():sha256((parent/n).read_bytes()).hexdigest() for n in ('2026-01-30.selection.json','2026-01-30.decision.json')});r.base.check(pins)
 r.base.save(out/'receipt.json',dict(status='ACTUAL_MONTHLY_PROVIDER_RISK_KERNEL_PASS',actual_searches=0,reused_selection_dates=calls,book_sha256=sha256((out/'book.json').read_bytes()).hexdigest(),source_hashes=pins,purpose='Three-session integration only. Actual parent initial cash and shares; no CAGR/performance claim.'));print('ACTUAL_MONTHLY_PROVIDER_RISK_KERNEL_PASS')
if __name__=='__main__':run()
