"""Private thin wrapper; original cap20 runner and original rejected gate remain immutable."""
import argparse,importlib.util
from pathlib import Path
from types import SimpleNamespace
from docs.candidates import cap20_alxn_may_assumption_20261105 as assumption
ROOT=Path(__file__).resolve().parents[2]
SELF='scripts/research/run_downside_cap20_alxn_assumption_20261105.py'
ADAPTER='docs/candidates/cap20_alxn_may_assumption_20261105.py'
def make_runner():
 spec=importlib.util.spec_from_file_location('isolated_cap20_alxn_assumption_runner',ROOT/'scripts/research/run_downside_cap20_account_20261105.py');runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
 original_prepare=runner.prepare;original_base=runner.base
 def prepare(window,extra_artifacts):
  original_base.need(window=='2021_2023' and extra_artifacts.count(assumption.PATH)==1,'EXPLICIT_ONE_EARLY_ASSUMPTION_REQUIRED')
  original_base.need(original_base.digest(assumption.PATH)==assumption.SHA,'ASSUMPTION_FIXED_PIN');artifact=original_base.read(assumption.PATH);original_base.check(artifact['source_hashes'])
  original_base.need((artifact['security_id'],artifact['start_exclusive'],artifact['end_inclusive'])==(assumption.SID,assumption.START,assumption.END) and artifact['admitted'] is False,'ORIGINAL_REJECTION_MUST_REMAIN')
  values=list(original_prepare(window,[p for p in extra_artifacts if p!=assumption.PATH]));pins=values[5]
  runner.merge_pins(pins,artifact['source_hashes']);pins.update({assumption.PATH:assumption.SHA,SELF:original_base.digest(SELF),ADAPTER:original_base.digest(ADAPTER)})
  values[8].append(dict(path=assumption.PATH,audit=dict(kind='ROOT_AUTHORIZED_RESEARCH_ASSUMPTION',absence_proven=False,production_admission=False,original_admitted=False,security_id=assumption.SID,start_exclusive=assumption.START,end_inclusive=assumption.END)))
  return tuple(values)
 def gate(**kwargs):
  original=original_base.action_gate(**kwargs)
  return assumption.apply_gate(original,window=kwargs['window'],arguments=kwargs['arguments'],until=kwargs['until'])
 def save(path,value):
  if path.name in ('contract.json','summary.json'):
   value=dict(value,conditional_assumption_dependency=dict(path=assumption.PATH,sha256=assumption.SHA,security_id=assumption.SID,start_exclusive=assumption.START,end_inclusive=assumption.END,absence_proven=False),production_admission=False,performance_claim_scope='CONDITIONAL_RESEARCH_ACCOUNT_ONLY')
  return original_base.save(path,value)
 runner.prepare=prepare;runner.base=SimpleNamespace(**{**original_base.__dict__,'action_gate':gate,'save':save});return runner
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--window',choices=['2021_2023'],required=True);p.add_argument('--output',required=True);p.add_argument('--freeze',required=True);p.add_argument('--parent',required=True);a=p.parse_args();make_runner().run(window=a.window,output=a.output,freeze_path=a.freeze,parent_path=a.parent)
