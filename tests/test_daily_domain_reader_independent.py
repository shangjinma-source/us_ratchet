"""Independent reader boundary probes; isolated SQLite and synthetic sources."""
import json
from tempfile import TemporaryDirectory
import unittest
from core.strategy_account_ledger import canonical
import test_strategy_daily_domain_packet_reader_v1 as fixtures


class IndependentDomainReaderTests(unittest.TestCase):
 def test_first_session_cannot_claim_rolling_without_parent(self):
  with TemporaryDirectory() as folder:
   account,root,reader,_=fixtures.DomainReaderTests().case(folder)
   path=root/'dynamic-runs/2026-11-02/terminal.json'
   terminal=json.loads(path.read_bytes());terminal['routes']['A']='ROLLING';path.write_bytes(canonical(terminal))
   with self.assertRaises(ValueError):
    reader(account.store.read(),account.target,account.clock[0])
 def test_server_identity_pin_is_not_ignored(self):
  with TemporaryDirectory() as folder:
   account,root,reader,_=fixtures.DomainReaderTests().case(folder)
   (root/'domain-identity.json').write_bytes(b'{}')
   with self.assertRaises(ValueError):
    reader(account.store.read(),account.target,account.clock[0])
 def test_current_cash_revision_rebind_is_read_only(self):
  with TemporaryDirectory() as folder:
   account,root,reader,_=fixtures.DomainReaderTests().case(folder)
   account.store.append(dict(event_id='independent-newcash',kind='CASH_CONFIRM',
    amount='123',cash_basis='TOTAL_UNINVESTED'),expected_revision=account.store.read()['revision'])
   before=account.store.path.read_bytes()
   result=reader(account.store.read(),account.target,account.clock[0])
   self.assertEqual(result['status'],'WAIT_POLICY_RELEASE')
   self.assertEqual(result['reviewed_securities'],['A','B'])
   self.assertEqual(account.store.path.read_bytes(),before)

if __name__=='__main__':unittest.main()
