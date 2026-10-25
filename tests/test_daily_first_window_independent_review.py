from copy import deepcopy
from hashlib import sha256
import json,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from core.strategy_account_ledger import canonical
import test_strategy_daily_first_window_v1 as fixture

class FirstWindowIndependentReview(unittest.TestCase):
 def test_identity_or_mark_cannot_replace_twenty_raw_prices(self):
  with TemporaryDirectory() as folder:
   f=fixture.FirstWindowTests();c,config,captured=f.case(folder)
   for mode in ('empty','mark_only','adjusted','missing_receipt','rss_notice','wrong_url'):
    with self.subTest(mode=mode):
     cap=deepcopy(captured)
     if mode=='missing_receipt':del cap['daily.receipt.json']
     elif mode=='wrong_url':
      rec=json.loads(cap['daily.receipt.json']);rec['url']='https://example.com/quote';cap['daily.receipt.json']=canonical(rec)
     elif mode=='rss_notice':
      raw=b'<rss><channel><item><title>BBB corporate action</title><pubDate>Mon, 02 Nov 2026 14:00:00 GMT</pubDate></item></channel></rss>'
      cap['official.response.bin']=raw;rec=json.loads(cap['official.receipt.json']);rec.update(raw_sha256=sha256(raw).hexdigest(),stored_bytes=len(raw));cap['official.receipt.json']=canonical(rec)
     else:
      doc=json.loads(cap['daily.response.bin']);row=doc['chart']['result'][0]
      if mode=='empty':row['timestamp']=[];row['indicators']['quote'][0]['close']=[];row['indicators']['adjclose'][0]['adjclose']=[]
      elif mode=='mark_only':row.pop('indicators');row['meta']['regularMarketPrice']=100
      else:row['indicators']['adjclose'][0]['adjclose'][0]=99
      raw=canonical(doc);cap['daily.response.bin']=raw;rec=json.loads(cap['daily.receipt.json']);rec.update(raw_sha256=sha256(raw).hexdigest(),stored_bytes=len(raw));cap['daily.receipt.json']=canonical(rec)
     result=f.run_case(folder,c,config,cap);self.assertEqual(result['status'],'WAIT_FIRST_WINDOW_REVIEW',result);self.assertIsNone(result['receipt'])
 def test_baseline_source_bytes_and_saved_mapping_are_required(self):
  with TemporaryDirectory() as folder:
   f=fixture.FirstWindowTests();c,config,captured=f.case(folder)
   cfg=deepcopy(config);cfg['unit_source_paths']={}
   result=f.run_case(folder,c,cfg,captured);self.assertEqual(result['reason'],'WAIT_UNIT_BASELINE')
   source=next(p for p in config['unit_source_paths'].values() if b'"chart"' in (Path(folder)/p).read_bytes())
   path=Path(folder)/source;path.write_bytes(path.read_bytes()+b' ')
   result=f.run_case(folder,c,config,captured);self.assertEqual(result['status'],'WAIT_FIRST_WINDOW_REVIEW');self.assertIsNone(result['receipt'])
 def test_reviewed_identity_and_mark_without_raw_overlap_wait(self):
  from unittest.mock import patch
  from data.strategy_account_action_capture import StrategyAccountActionCapture
  original=StrategyAccountActionCapture.__init__
  def initialize(instance,**kwargs):
   fetch=kwargs['fetch']
   def no_raw_history(*args,**options):
    result=fetch(*args,**options);doc=json.loads(result['body']);row=doc['chart']['result'][0]
    row.pop('timestamp',None);row.pop('indicators',None)
    return dict(result,body=canonical(doc))
   original(instance,**dict(kwargs,fetch=no_raw_history))
  with TemporaryDirectory() as folder:
   f=fixture.FirstWindowTests()
   with patch.object(StrategyAccountActionCapture,'__init__',initialize):c,config,captured=f.case(folder)
   result=f.run_case(folder,c,config,captured)
   self.assertEqual(result['status'],'WAIT_FIRST_WINDOW_REVIEW',result)
   self.assertEqual(result['reason'],'WAIT_BASELINE_RAW_PRICE_OVERLAP');self.assertIsNone(result['receipt'])
