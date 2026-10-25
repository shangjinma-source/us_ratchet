import json,unittest
from hashlib import sha256
from core.strategy_account_ledger import canonical
from data.strategy_daily_rolling_packet_reader_v3 import RollingSessionDailyPacketReaderV3
import test_strategy_daily_rolling_packet_reader_v3 as fixtures

class IndependentRollingPacketReview(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.RollingPacketReaderTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
  self.f.runner.run_day('2026-10-21');self.root=self.f.root
 def terminal(self):
  return self.root/'runs/2026-10-21/terminal.json'
 def test_null_policy_cannot_be_promoted_by_config(self):
  self.f.reader.release_path='unread-release.json';self.f.reader.release_sha='a'*64
  with self.assertRaisesRegex(ValueError,'REVIEWED_PARENT_POLICY_BINDING_REQUIRED'):self.f.read()
  self.assertFalse((self.root/'archive').exists())
 def test_exact_blob_tamper_rejected(self):
  terminal=json.loads(self.terminal().read_bytes());manifest=json.loads((self.root/terminal['manifest_reference']['path']).read_bytes())
  path=self.root/next(iter(manifest.values()))['path'];path.write_bytes(path.read_bytes()+b' ')
  with self.assertRaisesRegex(ValueError,'SOURCE_HASH_CHANGED'):self.f.read()
 def test_rehashed_manifest_escape_rejected(self):
  terminal=json.loads(self.terminal().read_bytes());path=self.root/terminal['manifest_reference']['path'];manifest=json.loads(path.read_bytes())
  next(iter(manifest.values()))['path']='../outside.bin';raw=canonical(manifest);path.write_bytes(raw)
  terminal['manifest_reference']['sha256']=sha256(raw).hexdigest();self.terminal().write_bytes(canonical(terminal))
  with self.assertRaisesRegex(ValueError,'PACKET_SOURCE_PATH_CHANGED'):self.f.read()
 def test_no_current_packet_does_not_use_previous(self):
  from datetime import datetime
  row=next(r for r in self.f.runner.f.sessions if r['date']=='2026-10-22')
  self.f.runner.f.f.now=datetime.fromisoformat(row['open'])
  result=self.f.read();self.assertEqual(result['reason'],'WAIT_NEW_SESSION_EVIDENCE');self.assertIsNone(result['signal'])

 def test_rehashed_receipt_cannot_change_parent_link(self):
  terminal=json.loads(self.terminal().read_bytes());rp=self.root/terminal['receipt_reference']['path'];receipt=json.loads(rp.read_bytes())
  mp=self.root/terminal['manifest_reference']['path'];manifest=json.loads(mp.read_bytes())
  oldname='server-parent/'+receipt['parent_review_sha256']+'.json'
  normalization=json.loads((self.root/manifest[oldname]['path']).read_bytes());normalization['parent_review_sha256']='0'*64
  raw=canonical(normalization);digest=sha256(raw).hexdigest();name='server-parent/'+digest+'.json';path='runs/2026-10-21/files/'+digest+'.bin'
  (self.root/path).write_bytes(raw);manifest[name]={'path':path,'sha256':digest};receipt['source_sha256'][name]=digest;receipt['parent_review_sha256']=digest
  for value,key,p in ((receipt,'receipt_reference',rp),(manifest,'manifest_reference',mp)):
   raw=canonical(value);p.write_bytes(raw);terminal[key]['sha256']=sha256(raw).hexdigest()
  self.terminal().write_bytes(canonical(terminal))
  with self.assertRaisesRegex(ValueError,'PACKET_PARENT_REVIEW_CHANGED'):self.f.read()
