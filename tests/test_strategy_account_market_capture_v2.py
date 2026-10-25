from datetime import datetime,timedelta,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest,json
from hashlib import sha256
from core.strategy_account_ledger import create_account
from data.strategy_account_market_capture_v2 import StrategyAccountMarketCaptureV2,verified_mark_transport
from test_strategy_account_market_capture import Identity,raw

class ClockTests(unittest.TestCase):
 def test_wait_and_capture_preserves_arrival(self):
  for lead in (1.1,1.34,2.0):
   with self.subTest(lead=lead),TemporaryDirectory()as d:
    observed=datetime(2026,10,16,13,32,tzinfo=timezone.utc);point=[observed-timedelta(seconds=lead)];arrival=point[0];mono=[0.0];calls=[]
    def sleep(seconds):point[0]+=timedelta(seconds=seconds);mono[0]+=seconds
    def fetch(t):calls.append(t);return raw(t)
    capture=StrategyAccountMarketCaptureV2(identity_resolver=Identity(),fetch=fetch,clock=lambda:point[0],max_workers=1,sleep=sleep,monotonic=lambda:mono[0])
    state=create_account('a');result=capture.capture(state=state,candidate_metadata={'A':{'ticker':'A'}},output_directory=Path(d)/'capture')
    self.assertEqual(calls,['A']);self.assertEqual(state,create_account('a'));self.assertGreaterEqual(point[0],observed)
    timing=next(json.loads(body)for name,body in result['files'].items()if name.endswith('.transport.json'))
    self.assertEqual(timing['network_received_at'],arrival.isoformat());self.assertGreaterEqual(datetime.fromisoformat(result['marks']['A']['captured_at']),observed)
    for name,digest in result['source_hashes'].items():self.assertEqual(sha256(result['files'][name]).hexdigest(),digest)
 def test_far_frozen_rollback_reject(self):
  observed=datetime(2026,10,16,13,32,tzinfo=timezone.utc)
  for mode in ('far','frozen','rollback'):
   with self.subTest(mode=mode):
    received=observed-timedelta(seconds=2.1 if mode=='far'else 1.34);point=[received];mono=[0.0]
    def sleep(seconds):
     mono[0]+=seconds
     if mode=='rollback':point[0]-=timedelta(seconds=seconds)
    with self.assertRaises(ValueError):verified_mark_transport(raw('A'),ticker='A',received_at=received,clock=lambda:point[0],sleep=sleep,monotonic=lambda:mono[0])
 def test_final_fsync_expiry_does_not_return(self):
  from unittest.mock import patch
  import os
  with TemporaryDirectory()as d:
   point=[datetime(2026,10,16,13,32,10,tzinfo=timezone.utc)];output=Path(d)/'capture';original=os.fsync
   def fsync(fd):
    original(fd)
    if (output/'transport-complete.json').exists():point[0]+=timedelta(seconds=180)
   capture=StrategyAccountMarketCaptureV2(identity_resolver=Identity(),fetch=raw,clock=lambda:point[0])
   with patch('data.strategy_account_market_capture_v2.os.fsync',side_effect=fsync):
    with self.assertRaisesRegex(ValueError,'LAST_QUOTE_STALE'):capture.capture(state=create_account('a'),candidate_metadata={'A':{'ticker':'A'}},output_directory=output)
   self.assertTrue((output/'transport-failed.json').exists())
 def test_stale_not_relaxed(self):
  with TemporaryDirectory()as d:
   capture=StrategyAccountMarketCaptureV2(identity_resolver=Identity(),fetch=raw,clock=lambda:datetime(2026,10,16,13,35,tzinfo=timezone.utc))
   with self.assertRaisesRegex(ValueError,'INCOMPLETE_MARK_DOMAIN'):capture.capture(state=create_account('a'),candidate_metadata={'A':{'ticker':'A'}},output_directory=Path(d)/'capture')

if __name__=='__main__':unittest.main()
