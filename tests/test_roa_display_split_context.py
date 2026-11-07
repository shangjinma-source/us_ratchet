import json,tempfile,unittest
from datetime import datetime,timezone
from core.strategy_account_ledger import canonical
from test_strategy_latest_display_charts_v1 import DisplayTests
class SplitTests(DisplayTests):
 def test_old_split_requires_baseline_and_post_split_fills(self):
  with tempfile.TemporaryDirectory() as folder:
   service,context,body,clock=self.setup_case(folder)
   doc=json.loads(body[0]);doc['chart']['result'][0]['events']={'splits':{'s':{'date':int(datetime(2026,10,13,13,30,tzinfo=timezone.utc).timestamp())}}};body[0]=canonical(doc)
   with self.assertRaisesRegex(ValueError,'DISPLAY_SPLIT_REVIEW_REQUIRED'):service.bars(security_id='SID')
   context.update(reviewed_split_through='2026-10-19',first_fill_session='2026-10-20')
   self.assertEqual(service.bars(security_id='SID')['status'],'DISPLAY_ONLY')
   context['first_fill_session']='2026-10-13'
   with self.assertRaisesRegex(ValueError,'DISPLAY_SPLIT_REVIEW_REQUIRED'):service.bars(security_id='SID')
