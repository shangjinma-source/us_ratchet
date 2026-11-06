import unittest
from copy import deepcopy
from scripts.research.screen_profitability_momentum_control_20261106 import build_decision

def fixture():
 ranked=[dict(security_id=str(i),issuer_id=str(i),ticker='T'+str(i),rank=i+1) for i in range(12)]
 rows=[]
 for i in range(12):
  fields={k:dict(value_exact=str(v),filed_dates=['2024-02-01']) for k,v in [('NetIncomeLoss',10),('NetCashProvidedByUsedInOperatingActivities',20),('Assets',100)]}
  rows.append(dict(security_id=str(i),status='DESCRIPTIVE_RAW_SAME_VERSION',fields=fields,accession='past'))
 return dict(decision_date='2024-04-30',ranked=ranked,selected=ranked[:10]),dict(results=[dict(cutoff='2024-03-28',rows=rows)])
class FixedArms(unittest.TestCase):
 def test_control_ignores_unavailable_but_reports_reason(self):
  r,p=fixture();p['results'][0]['rows'][0]['status']='FACTS_MISSING'
  result=build_decision(r,p,'CONTROL');self.assertEqual([x['security_id'] for x in result['selected']],[str(i) for i in range(10)])
  self.assertEqual(result['candidate_audit'][0]['financial_reason'],'FACTS_MISSING')
 def test_filter_keeps_original_order_and_distinguishes_missing(self):
  r,p=fixture();p['results'][0]['rows'][0]['status']='FACTS_MISSING';p['results'][0]['rows'][1]['fields']['NetIncomeLoss']['value_exact']='-1'
  out=build_decision(r,p,'PROFITABLE');self.assertEqual([x['security_id'] for x in out['selected']],[str(i) for i in range(2,12)])
  self.assertEqual(out['candidate_audit'][0]['financial_reason'],'FACTS_MISSING');self.assertEqual(out['candidate_audit'][1]['financial_reason'],'NI_OR_OCF_NOT_POSITIVE')
 def test_future_quarter_not_used(self):
  r,p=fixture();future=deepcopy(p['results'][0]);future['cutoff']='2024-06-28'
  for row in future['rows']:row['fields']['NetIncomeLoss']['value_exact']='-100'
  before=build_decision(r,p,'PROFITABLE');p['results'].append(future);self.assertEqual(build_decision(r,p,'PROFITABLE'),before)
 def test_future_filed_rejected(self):
  r,p=fixture();p['results'][0]['rows'][0]['fields']['Assets']['filed_dates']=['2024-04-01']
  with self.assertRaises(AssertionError):build_decision(r,p,'PROFITABLE')
if __name__=='__main__':unittest.main()
