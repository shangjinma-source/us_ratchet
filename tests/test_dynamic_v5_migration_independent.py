from copy import deepcopy
from hashlib import sha256
from tempfile import TemporaryDirectory
import unittest
from core.strategy_account_ledger import canonical
from data.strategy_daily_dynamic_factory_v5 import resolve_saved_context
import test_strategy_daily_dynamic_factory_v5 as author
from data.strategy_daily_domain_packet_reader_v2 import DomainSessionDailyPacketReaderV2

class MigrationBoundaryReview(unittest.TestCase):
 def test_reader_validates_migration_parent_and_next_day_new_root(self):
  from datetime import datetime
  with TemporaryDirectory() as folder:
   c,root,config,run,calls=author.MigrationFactoryTests().setup(folder)
   raw=canonical(config);(root/'new-config.json').write_bytes(raw)
   reader=DomainSessionDailyPacketReaderV2(root=root,configuration_path='new-config.json',configuration_sha256=sha256(raw).hexdigest(),archive_root='review-archive')
   self.assertEqual(run()['status'],'DYNAMIC_DOMAIN_PACKET_SAVED')
   result=reader(c.store.read(),c.target,c.clock[0])
   self.assertEqual(result['status'],'WAIT_POLICY_RELEASE',result)
   old=root/'dynamic-runs/2026-11-02/terminal.json';saved=old.read_bytes();old.unlink()
   with self.assertRaises(OSError):reader(c.store.read(),c.target,c.clock[0])
   old.write_bytes(saved)
   c.clock[0]=datetime.fromisoformat('2026-11-04T15:00:00+00:00')
   self.assertEqual(run()['status'],'DYNAMIC_DOMAIN_PACKET_SAVED')
   self.assertEqual(reader(c.store.read(),c.target,c.clock[0])['status'],'WAIT_POLICY_RELEASE')
 def test_only_exact_previous_day_uses_old_root_and_scope_is_immutable(self):
  with TemporaryDirectory() as folder:
   c,root,config,run,calls=author.MigrationFactoryTests().setup(folder)
   def resolve(value,day):
    return resolve_saved_context(root=root,config=value,configuration_sha256=sha256(canonical(value)).hexdigest(),day=day)
   old_path,old_hash=resolve(config,'2026-11-02')
   self.assertEqual(old_path,root/'dynamic-runs/2026-11-02')
   self.assertEqual(old_hash,config['prior_configuration']['sha256'])
   for day in ['2026-11-03','2026-11-04']:
    path,digest=resolve(config,day)
    self.assertEqual(path,root/'dynamic-runs-v5'/day)
    self.assertEqual(digest,sha256(canonical(config)).hexdigest())
   with self.assertRaisesRegex(ValueError,'HISTORY_BOUNDARY'):resolve(config,'2026-10-30')
   for key,value in [('account_id','other'),('identity',{'path':'other','sha256':'0'*64}),('calendar',{'path':'other','sha256':'0'*64}),('target_evidence_root','other')]:
    changed=deepcopy(config);changed[key]=value
    with self.subTest(field=key),self.assertRaisesRegex(ValueError,'SCOPE_CHANGED'):resolve(changed,'2026-11-03')
   changed=deepcopy(config);changed['source_pins'][0]['sha256']='0'*64
   with self.assertRaisesRegex(ValueError,'PINS_CHANGED'):resolve(changed,'2026-11-03')
   changed=deepcopy(config);changed['runs_root']='dynamic-runs'
   with self.assertRaisesRegex(ValueError,'RUNS_ROOT'):resolve(changed,'2026-11-03')
   self.assertEqual(calls,[])

if __name__=='__main__':unittest.main()
