from copy import deepcopy
from datetime import datetime,timezone
from tempfile import TemporaryDirectory
from hashlib import sha256
import json
import unittest
from data.strategy_monthly_supplement_capture import capture_supplement
from data.monthly_peak_raw_history import review_monthly_supplement
import test_monthly_peak_raw_history as raw_fixture
from pathlib import Path
from data.monthly_peak_exit_store import MonthlyPeakExitStore

class SupplementReviewTests(unittest.TestCase):
    def test_capture_review_restores_prefix_and_rejects_identity_continuity_action(self):
        inputs,series=raw_fixture.MonthlyRawHistoryTests().fixture()
        inputs['histories']['A']['closes']=inputs['histories']['A']['closes'][-1:]
        now=datetime(2026,10,6,14,tzinfo=timezone.utc)
        binding=dict(account_id='test',account_revision='r1',target_id='t1',session='2026-10-06')
        request=dict(account_id='test',state_revision='r1',window_start='2026-10-01T13:30:00+00:00',
            observed_floor=now.isoformat(),securities={'A':{'ticker':'TEST'}},current_target_quantities={'A':10})
        rss=b'<rss><channel><pubDate>Tue, 06 Oct 2026 13:00:00 GMT</pubDate><item><title>Other issuer notice</title><pubDate>Tue, 06 Oct 2026 13:00:00 GMT</pubDate></item></channel></rss>'
        with TemporaryDirectory() as folder:
            capture=capture_supplement(directory=folder,request=request,binding=binding,read_binding=lambda:binding,
                execute=True,clock=lambda:now,fetch_daily=lambda *a:dict(status=200,body=json.dumps(dict(chart=dict(error=None,result=[series]))).encode()),
                fetch_official=lambda:dict(status=200,body=rss))
            def review(c=capture,history=inputs,identities=None):
                return review_monthly_supplement(capture=c,request=request,binding=binding,inputs=history,
                    identities=identities or {'A':dict(ticker='TEST',exchange='NMS')},now=now)
            result=review();self.assertEqual(len(result['observations']),3);self.assertFalse(result['policy_approved'])
            risk=MonthlyPeakExitStore(Path(folder)/'risk.sqlite').advance(account_id='test',expected_previous_session=None,
                observations=result['observations'],baseline_targets={'A':10},target_month='2026-10')
            self.assertEqual(risk['effective_target_quantities'],{'A':0},'restored earlier exit must survive rebound')
            with self.assertRaises(ValueError):review(identities={'A':dict(ticker='WRONG',exchange='NMS')})
            changed=deepcopy(inputs);changed['histories']['A']['closes'][-1]['close']='111'
            with self.assertRaisesRegex(ValueError,'SUPPLEMENT_PRICE_CONTINUITY'):review(history=changed)
            changed=deepcopy(capture);name=changed['documents']['rss_raw'];raw=rss.replace(b'Other issuer',b'TEST')
            changed['files'][name]=raw;changed['source_hashes'][name]=sha256(raw).hexdigest()
            path=changed['documents']['rss_receipt'];receipt=json.loads(changed['files'][path]);receipt.update(raw_sha256=sha256(raw).hexdigest(),stored_bytes=len(raw))
            changed['files'][path]=json.dumps(receipt).encode();changed['source_hashes'][path]=sha256(changed['files'][path]).hexdigest()
            with self.assertRaisesRegex(ValueError,'SUPPLEMENT_ACTION_REVIEW_REQUIRED'):review(c=changed)

if __name__=='__main__':unittest.main()
