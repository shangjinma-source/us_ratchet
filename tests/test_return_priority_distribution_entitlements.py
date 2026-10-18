from copy import deepcopy
import unittest
from backtest.return_priority_distribution_entitlements import apply_distribution,value_distributions
D='2026-06-29'
def event(**kw):
 e=dict(event_id='HON_HONA',effective_date=D,parent_sid='HONold',child_sid='HONA',post_parent_sid='HONnew',eligible_parent_quantity=5,child_ratio='1/2',parent_ratio='1/2',eligibility_confirmed=True,ordered_steps_confirmed=True,parent_delivered_units_confirmed=True,source_references=['official'])
 e.update(kw);return e
def mark(p):return dict(date=D,price=p,source_references=['raw'])
class DistributionTests(unittest.TestCase):
 def test_ordered_compound_preserves_both_fractions_and_existing_child(self):
  s=dict(cash='10',shares={'HONold':5,'HONA':7});before=deepcopy(s)
  r=apply_distribution(state=s,event=event(),as_of=D)
  self.assertEqual(s,before);self.assertEqual(r['cash'],'10');self.assertEqual(r['shares'],{'HONold':0,'HONnew':2,'HONA':7})
  self.assertEqual([(x['kind'],x['units']) for x in r['distribution_rights']],[('CHILD_PENDING_WHOLE','2'),('CHILD_FRACTIONAL_CASH_RIGHT','1/2'),('PARENT_FRACTIONAL_CASH_RIGHT','1/2')])
  v=value_distributions(state=r,marks={'HONnew':mark('100'),'HONA':mark('50')},as_of=D)
  self.assertEqual(v['status'],'BLOCKED');self.assertEqual(len(v['blockers']),2);self.assertIsNone(v['total_equity']);self.assertEqual(v['available_cash'],'10')
  values={'HON_HONA':{k:dict(known_asof=D,amount='25',security_id='HONA' if k.startswith('CHILD') else 'HONnew',units='1/2',source_references=['contractual_settlement']) for k in ('CHILD_FRACTIONAL_CASH_RIGHT','PARENT_FRACTIONAL_CASH_RIGHT')}}
  v=value_distributions(state=r,marks={'HONnew':mark('100'),'HONA':mark('50')},as_of=D,fractional_cash_values=values)
  self.assertEqual(v['total_equity'],'710');self.assertEqual(v['available_cash'],'10');self.assertFalse(v['settlement_simulated'])
 def test_unsupported_capital_and_open_orders_rejected(self):
  for component in ({'merger_entitlements':[{'event_id':'other'}]}, {'receivable':'1'}, {'receivables':[1]}, {'pending_cash_flows':[1]}, {'undelivered_rights':[1]}, {'pending_orders':[1]}, {'reserved_cash':'1'}):
   state=dict(cash='0',shares={'HONold':5},**component)
   with self.assertRaisesRegex(ValueError,'Unsupported capital'):
    apply_distribution(state=state,event=event(),as_of=D)
   with self.assertRaisesRegex(ValueError,'Unsupported capital'):
    value_distributions(state=state,marks={},as_of=D)
 def test_fraction_settlement_must_bind_security_and_units(self):
  state=apply_distribution(state=dict(cash='0',shares={'HONold':1}),event=event(eligible_parent_quantity=1),as_of=D)
  for wrong in ({'security_id':'OTHER','units':'1/2'},{'security_id':'HONA','units':'1/4'},{}):
   values={'HON_HONA':{'CHILD_FRACTIONAL_CASH_RIGHT':dict(known_asof=D,amount='25',source_references=['contract'],**wrong)}}
   r=value_distributions(state=state,marks={},as_of=D,fractional_cash_values=values)
   self.assertEqual(r['status'],'BLOCKED');self.assertIsNone(r['total_equity']);self.assertEqual(r['state'],state)

 def test_comcast_parent_unchanged_pending_whole(self):
  e=event(event_id='COMCAST',parent_sid='CMCSA',post_parent_sid='CMCSA',child_sid='VSNT',eligible_parent_quantity=50,child_ratio='1/25',parent_ratio='1')
  r=apply_distribution(state=dict(cash='0',shares={'CMCSA':50}),event=e,as_of=D)
  self.assertEqual(r['shares'],{'CMCSA':50});self.assertEqual(r['distribution_rights'][0]['units'],'2')
  v=value_distributions(state=r,marks={'CMCSA':mark('30'),'VSNT':mark('10')},as_of=D);self.assertEqual(v['total_equity'],'1520');self.assertEqual(v['available_cash'],'0')
 def test_duplicate_missing_evidence_and_future_reject(self):
  s=dict(cash='0',shares={'HONold':5});r=apply_distribution(state=s,event=event(),as_of=D)
  with self.assertRaisesRegex(ValueError,'Duplicate'):apply_distribution(state=r,event=event(),as_of=D)
  for change in ({'source_references':[]},{'eligibility_confirmed':False},{'effective_date':'2026-06-30'}):
   with self.assertRaises(ValueError):apply_distribution(state=s,event=event(**change),as_of=D)
 def test_eligibility_not_inferred_and_missing_mark(self):
  e=event(eligible_parent_quantity=4,parent_ratio='1',post_parent_sid='HONold',child_ratio='1/4')
  r=apply_distribution(state=dict(cash='1',shares={'HONold':3}),event=e,as_of=D)
  self.assertEqual(r['distribution_rights'][0]['units'],'1');self.assertEqual(r['shares']['HONold'],3)
  v=value_distributions(state=r,marks={'HONold':mark('10')},as_of=D)
  self.assertEqual(v['status'],'BLOCKED');self.assertEqual(v['state'],r)
if __name__=='__main__':unittest.main()
