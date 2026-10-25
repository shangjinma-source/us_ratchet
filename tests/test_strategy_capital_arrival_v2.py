# All cash fixtures are synthetic; no broker balance or transfer amount is used.
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from threading import RLock
from datetime import datetime,timezone
from unittest.mock import patch
import unittest
from contextlib import closing
from core.strategy_account_store import StrategyAccountStore
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from core.strategy_profiled_capital_intent_journal import ProfiledCapitalIntentJournal
from core.strategy_profiled_capital_journal_v2 import ProfiledCapitalJournalV2
from data.strategy_capital_arrival_service_v2 import CapitalArrivalServiceV2

class LocalService(CapitalArrivalServiceV2):
 def _snapshot(self):return self.monthly.accounts.read(),self.monthly.current(),None

class ArrivalTests(unittest.TestCase):
 def fixture(self,temp):
  root=Path(temp);a=StrategyAccountStore(root/'a.db');a.initialize('a',operation_id='init')
  a.append(dict(event_id='cash',kind='CASH_CONFIRM',amount='10234.56',cash_basis='AVAILABLE_AFTER_RESERVATIONS'),expected_revision=a.read()['revision'])
  target=dict(target_id='a'*64,payload=dict(account_id='a',target_month='2026-10'))
  j=ProfiledCapitalJournalV2(root/'v2.db');j.initialize_from_legacy(ProfiledCapitalIntentJournal(root/'old.db'))
  m=SimpleNamespace(accounts=a,current=lambda:target,targets=StrategyMonthlyTargetStore(root/'targets.db'),snapshot_operation=lambda:RLock(),clock=lambda:datetime.now(timezone.utc))
  return LocalService(monthly=m,journal=j,validate_code=lambda:None),a,j,target
 def test_arrival_once_and_unknown_response(self):
  with TemporaryDirectory() as t:
   s,a,j,target=self.fixture(t);request=dict(event_id='arrival',contribution_amount='2345.67',expected_revision=a.read()['revision'],previous_target_id=target['target_id'])
   with patch.object(s,'record',side_effect=OSError('disconnect')):
    with self.assertRaises(OSError):s.arrive(**request)
   self.assertEqual(s.status(event_id='arrival')['status'],'CASH_RECORDED')
   self.assertEqual(a.read()['available_cash'],'1258023/100')
   result=s.arrive(**request);self.assertEqual(result['status'],'INTENT_RECORDED');self.assertTrue(result['credited'])
   before=a.path.read_bytes();s.arrive(**request);self.assertEqual(a.path.read_bytes(),before)
   with self.assertRaisesRegex(ValueError,'EVENT_CONFLICT'):s.arrive(**dict(request,contribution_amount='1'))
   with self.assertRaisesRegex(ValueError,'CREDIT_CANNOT_WITHDRAW'):s.withdraw(event_id='arrival')
 def test_withdraw_preserves_claim_and_new_event_allowed(self):
  with TemporaryDirectory() as t:
   s,a,j,target=self.fixture(t)
   s.record(event_id='expected',contribution_amount='2345.67',expected_revision=a.read()['revision'],previous_target_id=target['target_id'])
   j.claim_selection_once('expected',account_state=a.read(),previous_target=target)
   before=a.path.read_bytes();self.assertEqual(s.withdraw(event_id='expected')['status'],'WITHDRAWN');self.assertEqual(a.path.read_bytes(),before)
   with closing(j._connect()) as c:self.assertEqual(c.execute('select count(*) from claims').fetchone()[0],1)
   s.arrive(event_id='received',contribution_amount='2345.67',expected_revision=a.read()['revision'],previous_target_id=target['target_id'])
   self.assertTrue(j.claim_selection_once('received',account_state=a.read(),previous_target=target)['may_start_selection'])
   with self.assertRaisesRegex(ValueError,'WITHDRAWN'):j.claim_selection_once('expected',account_state=a.read(),previous_target=target)
 def test_uncredited_arrival_can_be_withdrawn(self):
  with TemporaryDirectory() as t:
   s,a,j,target=self.fixture(t);request=dict(event_id='interrupted',contribution_amount='10',expected_revision=a.read()['revision'],previous_target_id=target['target_id'])
   before=a.path.read_bytes()
   with patch.object(a,'append',side_effect=OSError('network')):
    with self.assertRaises(OSError):s.arrive(**request)
   self.assertFalse(s.status(event_id='interrupted')['credited'])
   self.assertEqual(s.withdraw(event_id='interrupted')['status'],'WITHDRAWN')
   with self.assertRaisesRegex(ValueError,'WITHDRAWN'):s.arrive(**request)
   self.assertEqual(before,a.path.read_bytes())
 def test_stale_revision_does_not_credit(self):
  with TemporaryDirectory() as t:
   s,a,j,target=self.fixture(t);before=a.path.read_bytes()
   with self.assertRaisesRegex(ValueError,'STALE'):s.arrive(event_id='new',contribution_amount='1',expected_revision='0'*64,previous_target_id=target['target_id'])
   self.assertEqual(before,a.path.read_bytes())

if __name__=='__main__':unittest.main()

