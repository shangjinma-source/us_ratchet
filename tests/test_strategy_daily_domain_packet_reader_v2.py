from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime
from hashlib import sha256
import unittest
from core.strategy_account_ledger import canonical
from data.strategy_daily_domain_packet_reader_v2 import DomainSessionDailyPacketReaderV2
import test_strategy_daily_dynamic_factory_v5 as fixture

class MigrationReaderTests(unittest.TestCase):
 def test_old_parent_migration_next_day_new_parent_and_closure(self):
  with TemporaryDirectory() as folder:
   c,root,config,run,calls=fixture.MigrationFactoryTests().setup(folder)
   raw=canonical(config);(root/'reader.json').write_bytes(raw)
   reader=DomainSessionDailyPacketReaderV2(root=root,configuration_path='reader.json',configuration_sha256=sha256(raw).hexdigest(),archive_root=None)
   self.assertEqual(run()['status'],'DYNAMIC_DOMAIN_PACKET_SAVED')
   self.assertEqual(reader(c.store.read(),c.target,c.clock[0])['status'],'WAIT_POLICY_RELEASE')
   c.clock[0]=datetime.fromisoformat('2026-11-04T15:00:00+00:00')
   self.assertEqual(run()['status'],'DYNAMIC_DOMAIN_PACKET_SAVED')
   self.assertEqual(reader(c.store.read(),c.target,c.clock[0])['status'],'WAIT_POLICY_RELEASE')
   parent=root/'dynamic-runs-v5/2026-11-03/terminal.json';parent.rename(parent.with_suffix('.saved'))
   with self.assertRaises((OSError,ValueError)):reader(c.store.read(),c.target,c.clock[0])
   self.assertEqual(calls,['BBB','BBB'])
 def test_migration_old_hash_and_previous_bytes_are_mandatory(self):
  with TemporaryDirectory() as folder:
   c,root,config,run,calls=fixture.MigrationFactoryTests().setup(folder)
   raw=canonical(config);(root/'reader.json').write_bytes(raw)
   reader=DomainSessionDailyPacketReaderV2(root=root,configuration_path='reader.json',configuration_sha256=sha256(raw).hexdigest(),archive_root=None)
   self.assertEqual(run()['status'],'DYNAMIC_DOMAIN_PACKET_SAVED')
   parent=root/'dynamic-runs/2026-11-02/terminal.json';parent.rename(parent.with_suffix('.saved'))
   with self.assertRaises((OSError,ValueError)):reader(c.store.read(),c.target,c.clock[0])
   self.assertEqual(calls,['BBB'])
if __name__=='__main__':unittest.main()
