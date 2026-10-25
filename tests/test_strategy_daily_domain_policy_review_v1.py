"""Explicit fixture approval only: never modifies a real release or account."""
from copy import deepcopy
from hashlib import sha256
import json
from tempfile import TemporaryDirectory
import unittest
from core.strategy_account_ledger import canonical
from data.strategy_daily_domain_policy_review_v1 import review_domain_policy
import test_strategy_daily_domain_packet_reader_v1 as fixtures


class DomainPolicyReviewTests(unittest.TestCase):
 def setup(self,folder):
  c,root,reader,before=fixtures.DomainReaderTests().case(folder)
  terminal=json.loads((root/'dynamic-runs/2026-11-02/terminal.json').read_bytes())
  packets={}
  for sid,refs in terminal['packets'].items():
   raw=(root/refs['receipt_reference']['path']).read_bytes()
   manifest=json.loads((root/refs['manifest_reference']['path']).read_bytes())
   packets[sid]=dict(receipt_bytes=raw,trusted_receipt_sha256=sha256(raw).hexdigest(),
    files={name:(root/ref['path']).read_bytes() for name,ref in manifest.items()})
  state=c.store.read()
  domain=dict(account_id=state['account_id'],account_revision=state['revision'],
   target_id=c.target['target_id'],securities={sid:{} for sid in packets})
  args=dict(state=state,target=c.target,now=c.clock[0].isoformat(),event_id='isolated-explicit-review',
   domain=domain,packets=packets,release_bytes=(root/'release.json').read_bytes(),
   trusted_release_sha256=sha256((root/'release.json').read_bytes()).hexdigest(),
   calendar_bytes=(root/'calendar.json').read_bytes())
  self.assertTrue(json.loads(args['release_bytes'])['fixture_only'])
  return c,root,args
 def test_actual_double_security_packet_explicit_binding_keeps_source_time(self):
  with TemporaryDirectory() as folder:
   c,root,args=self.setup(folder);before=c.store.path.read_bytes();original=deepcopy(args)
   result=review_domain_policy(**args)
   self.assertEqual(result['status'],'DOMAIN_POLICY_REVIEW_READY_NOT_PUBLISHED')
   self.assertFalse(result['published']);self.assertFalse(result['policy_approved'])
   self.assertFalse(result['account_mutated'])
   self.assertEqual(set(result['packets']),{'A','B'})
   for sid,packet in result['packets'].items():
    receipt=json.loads(packet['receipt_bytes']);old=json.loads(args['packets'][sid]['receipt_bytes'])
    self.assertEqual(receipt['source_received_at'],old['source_received_at'])
    self.assertEqual(receipt['market_asof'],old['market_asof'])
    self.assertEqual(receipt['available_at'],args['now'])
    name='policy-originals/'+args['packets'][sid]['trusted_receipt_sha256']+'.json'
    self.assertEqual(packet['files'][name],args['packets'][sid]['receipt_bytes'])
    for path,raw in args['packets'][sid]['files'].items():self.assertEqual(packet['files'][path],raw)
   self.assertEqual(args,original);self.assertEqual(c.store.path.read_bytes(),before)
 def test_missing_domain_cannot_bind_partial_release(self):
  with TemporaryDirectory() as folder:
   c,root,args=self.setup(folder);args['packets'].pop('A')
   result=review_domain_policy(**args)
   self.assertEqual(result['status'],'WAIT_COMPLETE_SECURITY_DOMAIN')
   self.assertIsNone(result['receipt']);self.assertIsNone(result['packets'])
 def test_future_approval_profile_and_rebinding_rejected(self):
  with TemporaryDirectory() as folder:
   c,root,args=self.setup(folder);before=c.store.path.read_bytes()
   for kind in ('future','profile','releasehash','already-bound'):
    changed=deepcopy(args)
    if kind=='already-bound':
     for sid,packet in changed['packets'].items():
      receipt=json.loads(packet['receipt_bytes']);receipt['release_sha256']=args['trusted_release_sha256']
      raw=canonical(receipt);packet.update(receipt_bytes=raw,trusted_receipt_sha256=sha256(raw).hexdigest())
    elif kind=='releasehash':changed['trusted_release_sha256']='0'*64
    else:
     release=json.loads(changed['release_bytes'])
     if kind=='future':release['approved_at']='2099-01-01T00:00:00Z'
     if kind=='profile':release['selector_profile']='wrong-profile'
     raw=canonical(release);changed.update(release_bytes=raw,trusted_release_sha256=sha256(raw).hexdigest())
    with self.subTest(kind=kind),self.assertRaises(ValueError):review_domain_policy(**changed)
   self.assertEqual(c.store.path.read_bytes(),before)

if __name__=='__main__':unittest.main()
