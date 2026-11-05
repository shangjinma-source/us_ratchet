"""Fixed late AZN zero-recovery branch. Original ledger engine/source stays frozen."""
import argparse,importlib.util
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from docs.candidates import cap20_azn_zero_recovery_20261105 as a
ROOT=Path(__file__).resolve().parents[2]
SELF='scripts/research/run_downside_cap20_azn_zero_recovery_20261105.py';ADAPTER='docs/candidates/cap20_azn_zero_recovery_20261105.py';POLICY='research_contracts/cap20_azn_zero_recovery_20261105.json';POLICY_SHA='726f02854d97b2962da2796b7158687e99bd5855875d14021acd7c6882c05550'
def make_runner():
 spec=importlib.util.spec_from_file_location('private_cap20_azn_zero_runner',ROOT/'scripts/research/run_downside_cap20_account_20261105.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r);original_prepare=r.prepare;base=r.base;util=r.importlib.util
 def prepare(window,artifacts):
  base.need(window=='2024_2026' and artifacts.count(POLICY)==1 and base.digest(POLICY)==POLICY_SHA,'EXACT_ZERO_RECOVERY_POLICY');policy=base.read(POLICY);base.check(policy['source_hashes']);values=list(original_prepare(window,[n for n in artifacts if n!=POLICY]));doc=values[0]
  official=base.read('tmp/next12_action_inputs_20261015_v2/action_inputs.json');base.check(official['source_hashes']);r.merge_pins(values[5],official['source_hashes']);r.merge_pins(values[5],policy['source_hashes'])
  term=next(x for x in official['unsupported_conversions'] if x['old_sid']==a.OLD);base.need(term['date']==a.DAY and term['new_sid']==a.NEW and term['ratio']=='1/2' and term['conversion_evidence_available'] is True,'OFFICIAL_CONVERSION_COORDINATES')
  refs=term['source_references']+['research_contracts/next12_dtc_conversion_model_20261015_v1.json',POLICY]
  event=dict(type='ads_conversion',date=a.DAY,event_id=a.EVENT,security_id=a.OLD,new_security_id=a.NEW,new_shares='1',old_shares='2',delivery_model='DTC_BENEFICIAL_INTERESTS',source_references=refs)
  for key in ('actions','provider_actions'):
   base.need(not any(e.get('security_id')==a.OLD and e.get('date')==a.DAY for e in doc['assembled'][key]),'NO_DUPLICATE_AZN_EVENT');doc['assembled'][key].append(deepcopy(event));doc['assembled'][key].sort(key=lambda e:(e['date'],e['security_id']))
  doc['assembled']['account_model']='DTC_BENEFICIAL_INTERESTS';base.need(not doc['assembled']['distribution_fractional_cash_values'],'NO_FAKE_KNOWN_SETTLEMENT');values[5].update({POLICY:POLICY_SHA,SELF:base.digest(SELF),ADAPTER:base.digest(ADAPTER)})
  for name in refs:
   if name!=POLICY:base.need(name in values[5],'OFFICIAL_REF_PIN_REQUIRED:'+name)
  values[8].append(dict(path=POLICY,audit=dict(kind=a.SCOPE,event=event,production_eligible=False,full_account_equity_certified=False,policy=policy)));return tuple(values)
 def gate(**kw):
  original=base.action_gate(**kw)
  if kw['window']!='2024_2026' or kw['arguments']['decision_date']!='2026-01-30':return original
  base.need(kw['active']==a.DAY and kw['until']=='2026-02-27' and kw['arguments']['account_state']['shares'].get(a.OLD)==49 and kw['selected']['target_quantities'].get(a.OLD,0)==kw['selected']['target_quantities'].get(a.NEW,0)==0,'EXACT49_EXIT_CONTEXT')
  result=deepcopy(original);matched=[];remaining=[]
  for e in original['unmapped_events']:
   if e.get('security_id')==a.OLD and e.get('date')==a.DAY and e['kind']=='splits' and e.get('provider_payload',{}).get('splitRatio')=='1:2':matched.append(e)
   elif e.get('security_id')==a.OLD and e.get('date')==a.DAY and e['kind']=='IDENTITY_CONVERSION' and e.get('new_sid')==a.NEW and e.get('share_ratio')=='1/2':matched.append(e)
   else:remaining.append(e)
  base.need(len(matched)==2,'EXACT_TWO_AZN_BARRIERS');result['unmapped_events']=remaining;result['admitted']=not remaining and not result['missing_action_streams'];result['original_gate_rejection_preserved']=original;result['conditional_assumptions']=[dict(kind=a.SCOPE,policy=POLICY,sha256=POLICY_SHA,production_eligible=False)];return result
 def save(path,value):
  if path.name in ('contract.json','summary.json'):value=dict(value,azn_zero_recovery_assumption=dict(path=POLICY,sha256=POLICY_SHA,event_id=a.EVENT,fractional_units='1/2',recovery_assumed='0',payment_assumed=False),production_eligible=False,full_account_equity_certified=False)
  return base.save(path,value)
 def make_spec(name,path,*args,**kwargs):
  spec=util.spec_from_file_location(name,path,*args,**kwargs)
  if str(path).replace('\\','/').endswith('/docs/candidates/qqq_risk_budget_account_runner.py'):
   loader=spec.loader
   class Loader:
    def create_module(self,spec):return loader.create_module(spec)
    def exec_module(self,module):
     loader.exec_module(module)
     bs=util.spec_from_file_location('private_zero_recovery_book',ROOT/'backtest/historical_dividend_next_open_book_research.py');bm=util.module_from_spec(bs);bs.loader.exec_module(bm);a.install_book_module(bm);module.run_next_open_book=bm.run_next_open_book
     build=module.build_cost_monthly_quantity_provider
     def build_view(**options):
      provider=build(**options)
      def view_provider(**state):
       forwarded=dict(state);forwarded['state']=a.sizing_view(state['state']);return provider(**forwarded)
      return view_provider
     module.build_cost_monthly_quantity_provider=build_view
   spec.loader=Loader()
  return spec
 r.prepare=prepare;r.base=SimpleNamespace(**{**base.__dict__,'action_gate':gate,'save':save});r.importlib=SimpleNamespace(util=SimpleNamespace(spec_from_file_location=make_spec,module_from_spec=util.module_from_spec));return r
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--window',choices=['2024_2026'],required=True);p.add_argument('--output',required=True);p.add_argument('--freeze',required=True);p.add_argument('--parent',required=True);x=p.parse_args();make_runner().run(window=x.window,output=x.output,freeze_path=x.freeze,parent_path=x.parent)
