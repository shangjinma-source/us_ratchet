from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest,json
from core.strategy_account_ledger import canonical
from data.strategy_account_action_capture import StrategyAccountActionCapture
from data.strategy_account_unit_review import review_interval
from data.current_quantity_v2_paper_action_sources import daily_url
from test_strategy_account_unit_review import fixture,NOW

class ActionTests(unittest.TestCase):
 def request(self):return dict(account_id='review-test',state_revision='revision',window_start='2026-10-14T20:00:00Z',observed_floor=NOW.isoformat(),securities={'S':{'ticker':'AAA'}},current_target_quantities={})
 def fetch(self,ticker,start,end):return dict(status=200,url=daily_url(ticker,start,end),body=canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY'),events={})]))))
 def rss(self):return dict(status=200,body=b'<rss><channel><title>Nasdaq</title><item><title>Unrelated</title><pubDate>Fri, 16 Oct 2026 13:00:00 GMT</pubDate></item></channel></rss>')
 def test_real_review_consumer_complete_domain_and_no_retry(self):
  with TemporaryDirectory() as d:
   directory=Path(d)/'capture';args=fixture();request=self.request();request['state_revision']=args['state']['revision']
   provider=StrategyAccountActionCapture(fetch=self.fetch,rss_fetch=self.rss,clock=lambda:NOW)
   package=provider.capture(request,directory);args['action_package']=package
   self.assertEqual(review_interval(**args)['status'],'CONDITIONAL_CURRENT_UNITS_REVIEWED')
   self.assertEqual(set(package['documents']['action_receipts']),{'S'})
   receipt=json.loads(package['files'][package['documents']['action_receipts']['S']]);self.assertEqual(receipt['requested_through'],NOW.isoformat())
   with self.assertRaises(FileExistsError):provider.capture(request,directory)
 def test_failure_delay_response_url_and_all_domain_not_dropped(self):
  for mode in ('transport','delay','url'):
   with self.subTest(mode=mode),TemporaryDirectory() as d:
    time=[NOW];calls=[];rsscalls=[]
    def fetch(t,start,end):
     calls.append(t)
     if mode=='transport' and t=='BBB':raise OSError('private error')
     result=self.fetch(t,start,end)
     if mode=='delay':time[0]+=timedelta(seconds=121)
     if mode=='url':result['url']='https://invalid.test/'
     return result
    request=self.request();request['securities']['B']={'ticker':'BBB'}
    provider=StrategyAccountActionCapture(fetch=fetch,rss_fetch=lambda:rsscalls.append(1),clock=lambda:time[0],max_workers=1)
    directory=Path(d)/'capture'
    with self.assertRaises(ValueError):provider.capture(request,directory)
    self.assertTrue((directory/'failed.json').exists());self.assertFalse((directory/'complete.json').exists());self.assertEqual(rsscalls,[])
    self.assertNotIn('private error',(directory/'failures.json').read_text())
 def test_duplicate_ticker_and_future_floor_zero_fetch(self):
  for mode in ('duplicate','future'):
   with self.subTest(mode=mode),TemporaryDirectory() as d:
    request=self.request()
    if mode=='duplicate':request['securities']['B']={'ticker':'AAA'}
    else:request['observed_floor']=(NOW+timedelta(seconds=1)).isoformat()
    provider=StrategyAccountActionCapture(fetch=lambda *a:self.fail('no fetch'),clock=lambda:NOW)
    with self.assertRaises(ValueError):provider.capture(request,Path(d)/'capture')
    self.assertFalse((Path(d)/'capture').exists())
 def test_rss_delay_blocks_and_retains_raw(self):
  with TemporaryDirectory() as d:
   time=[NOW]
   def rss():time[0]+=timedelta(seconds=121);return self.rss()
   provider=StrategyAccountActionCapture(fetch=self.fetch,rss_fetch=rss,clock=lambda:time[0])
   directory=Path(d)/'capture'
   with self.assertRaisesRegex(ValueError,'ACTION_CAPTURE_WINDOW_EXPIRED'):provider.capture(self.request(),directory)
   self.assertEqual(len(list(directory.glob('*.xml'))),1);self.assertFalse((directory/'complete.json').exists())

if __name__=='__main__':unittest.main()
