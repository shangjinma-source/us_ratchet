"""New private June exit layer over unchanged frozen May wrapper."""
import argparse
from types import SimpleNamespace
from docs.candidates import cap20_alxn_june_exit_assumption_20261105 as assumption
from scripts.research.run_downside_cap20_alxn_assumption_20261105 import make_runner as may_runner
SELF='scripts/research/run_downside_cap20_alxn_june_exit_20261105.py'
ADAPTER='docs/candidates/cap20_alxn_june_exit_assumption_20261105.py'
def make_runner():
 runner=may_runner();original_prepare=runner.prepare;original_base=runner.base;original_util=runner.importlib.util
 def prepare(window,extra_artifacts):
  original_base.need(extra_artifacts.count(assumption.PATH)==1,'ONE_SHORT_EXIT_ARTIFACT');original_base.need(original_base.digest(assumption.PATH)==assumption.SHA,'SHORT_EXIT_FIXED_PIN');artifact=original_base.read(assumption.PATH);original_base.check(artifact['source_hashes'])
  scope=artifact['current_scope'];original_base.need(artifact['security_id']==assumption.SID and scope['start_exclusive']==assumption.START and scope['end_inclusive']==assumption.END and scope['held_quantity']==24 and scope['new_target_quantity']==0,'EXACT_SHORT_EXIT_SCOPE')
  values=list(original_prepare(window,[p for p in extra_artifacts if p!=assumption.PATH]));runner.merge_pins(values[5],artifact['source_hashes']);values[5].update({assumption.PATH:assumption.SHA,SELF:original_base.digest(SELF),ADAPTER:original_base.digest(ADAPTER)})
  values[8].append(dict(path=assumption.PATH,audit=dict(kind='CONDITIONAL_SINGLE_SESSION_EXIT',security_id=assumption.SID,start_exclusive=assumption.START,end_inclusive=assumption.END,absence_proven=False,production_admission=False,requires_complete_exit=True)))
  return tuple(values)
 def gate(**kwargs):return assumption.apply_gate(original_base.action_gate(**kwargs),window=kwargs['window'],arguments=kwargs['arguments'],selected=kwargs['selected'],active=kwargs['active'],until=kwargs['until'])
 def save(path,value):
  if path.name in ('contract.json','summary.json'):
   from docs.candidates import cap20_alxn_may_assumption_20261105 as may
   value=dict(value,conditional_assumption_dependencies=[dict(path=a.PATH,sha256=a.SHA,security_id=a.SID,start_exclusive=a.START,end_inclusive=a.END,absence_proven=False) for a in (may,assumption)],production_admission=False)
  return original_base.save(path,value)
 def make_spec(name,path,*args,**kwargs):
  spec=original_util.spec_from_file_location(name,path,*args,**kwargs)
  if str(path).replace('\\','/').endswith('/docs/candidates/qqq_risk_budget_account_runner.py'):
   loader=spec.loader
   class CheckedLoader:
    def create_module(self,spec):return loader.create_module(spec)
    def exec_module(self,module):
     loader.exec_module(module);original_book=module.run_next_open_book
     def checked_book(**book_args):
      provider=book_args['order_provider']
      def checked_provider(**state):assumption.assert_exit(state['state']['daily_ledger']);return provider(**state)
      book_args['order_provider']=checked_provider;book=original_book(**book_args);assumption.assert_exit(book['daily_ledger']);return book
     module.run_next_open_book=checked_book
   spec.loader=CheckedLoader()
  return spec
 runner.prepare=prepare;runner.base=SimpleNamespace(**{**original_base.__dict__,'action_gate':gate,'save':save});runner.importlib=SimpleNamespace(util=SimpleNamespace(spec_from_file_location=make_spec,module_from_spec=original_util.module_from_spec));return runner
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--window',choices=['2021_2023'],required=True);p.add_argument('--output',required=True);p.add_argument('--freeze',required=True);p.add_argument('--parent',required=True);a=p.parse_args();make_runner().run(window=a.window,output=a.output,freeze_path=a.freeze,parent_path=a.parent)
