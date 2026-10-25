from tempfile import TemporaryDirectory
from copy import deepcopy
import unittest
from data.strategy_daily_composition_v4 import DailyCompositionV4
from test_daily_composition_v3 import CompositionTests,POLICY

class BuyDataWaitTests(unittest.TestCase):
 def test_notice_failure_never_falls_back(self):
  with TemporaryDirectory() as directory:
   c=CompositionTests().setup_case(directory,"A")
   c.store.append(dict(event_id="cash-data-wait-test",kind="CASH_CONFIRM",amount="100",cash_basis="TOTAL_UNINVESTED"),expected_revision=c.state['revision'])
   c.state=c.store.read();before=c.store.path.read_bytes();calls=[]
   def denied(**kwargs):
    calls.append(1);raise ValueError('KNOWN_NOTICE_REQUIRES_REVIEW')
   c.provider.limits=denied
   service=DailyCompositionV4(monthly_service=c.monthly,evidence_reader=c.reader,execution_provider=c.provider.execution,clock=lambda:c.clock[0],policy_execution_enabled=True,policy_id=POLICY,fee_bps="10")
   with self.assertRaisesRegex(ValueError,'KNOWN_NOTICE_REQUIRES_REVIEW'):
    service.preview(expected_revision=c.state['revision'],target_id=c.target['target_id'])
   self.assertEqual(calls,[1]);self.assertEqual(c.store.path.read_bytes(),before)
 def test_buy_gap_preserves_sell_and_account(self):
  with TemporaryDirectory() as directory:
   c=CompositionTests().setup_case(directory,"A")
   c.store.append(dict(event_id="cash-data-wait-test",kind="CASH_CONFIRM",amount="100",cash_basis="TOTAL_UNINVESTED"),expected_revision=c.state["revision"])
   c.state=c.store.read();before=c.store.path.read_bytes();target=deepcopy(c.target)
   original=c.provider.limits;calls=[]
   def limits(**kwargs):
    calls.append(deepcopy(kwargs['target_quantities']))
    if kwargs['target_quantities'].get('B',0)>0:raise ValueError('RAW_NUMERIC_REQUIRED')
    return original(**kwargs)
   c.provider.limits=limits
   service=DailyCompositionV4(monthly_service=c.monthly,evidence_reader=c.reader,execution_provider=c.provider.execution,clock=lambda:c.clock[0],policy_execution_enabled=True,policy_id=POLICY,fee_bps="10")
   result=service.preview(expected_revision=c.state['revision'],target_id=c.target['target_id'])
   self.assertEqual(result['status'],'READY')
   self.assertEqual([(x['security_id'],x['side'],x['quantity']) for x in result['new_orders']],[('A','SELL',14)])
   self.assertEqual(result['waiting_data'],[dict(security_id='B',quantity=10,reason='WAIT_BUY_MINUTE_DATA')])
   self.assertEqual(result['effective_target_quantities']['B'],10)
   self.assertEqual(result['waiting_cash'],[])
   self.assertEqual(c.store.path.read_bytes(),before);self.assertEqual(c.target,target)
   self.assertEqual(len(calls),2)
if __name__=='__main__':unittest.main()

