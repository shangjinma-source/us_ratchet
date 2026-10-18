import unittest,json
from copy import deepcopy
from datetime import datetime,timedelta
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch
import test_current_quantity_v2_current_cash_plan as base
from test_current_quantity_v2_current_cash_continuation import fixture as cash_fixture
from data.current_quantity_v2_paper_action_sources import PaperActionEvidenceSources
from data.current_quantity_v2_paper_review import review_request,derive_paper_review,validate_paper_review
from data.current_quantity_v2_paper_review_provider import DerivedPaperReviewProvider

def fixture(args):
    state,_,now=cash_fixture(args);clock=[datetime.fromisoformat(now)];calls=[]
    def daily(ticker,start,end):
        calls.append(ticker)
        stamps=[int((end-timedelta(days=8)).timestamp()),int(end.timestamp())]
        chart=dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1d'),timestamp=stamps,
            indicators={'quote':[dict(open=[10,10],high=[11,11],low=[9,9],close=[10,10],volume=[10,10])]},events={})
        return dict(status=200,body=json.dumps({'chart':{'result':[chart],'error':None}}).encode())
    def rss():
        calls.append('RSS');return dict(status=200,body=b'<rss><channel><item><title>Unrelated notice</title><pubDate>Wed, 14 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>')
    source=PaperActionEvidenceSources(fetch=daily,rss_fetch=rss,clock=lambda:clock[0])
    return state,clock,calls,source

class ReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):base.CurrentCashTests.setUpClass();cls.args=base.CurrentCashTests.args
    @classmethod
    def tearDownClass(cls):base.CurrentCashTests.tearDownClass()
    def test_capture_saved_replay_no_callback_and_no_chain_embedding(self):
        state,clock,calls,source=fixture(self.args)
        with TemporaryDirectory() as folder:
            provider=DerivedPaperReviewProvider(storage_root=Path(folder)/'proofs',evidence_reader=source,clock=lambda:clock[0])
            self.assertFalse((Path(folder)/'proofs').exists());p=provider.capture({'state':state})
            self.assertEqual(calls,['AAA','BBB','RSS']);r=json.loads(p['files'][p['account_review_path']])
            self.assertEqual(r['derived_evidence']['request']['securities'].keys(),{'A','B'})
            self.assertIsNone(r['derived_evidence']['baseline_package']);self.assertNotIn('state',r['derived_evidence'])
            source.capture=lambda *a:(_ for _ in ()).throw(AssertionError('fetch'))
            self.assertEqual(provider.read({'state':state}),p)
            other=DerivedPaperReviewProvider(storage_root=folder,evidence_reader=source,clock=lambda:clock[0])
            self.assertEqual(other.read({'state':state},frozen_package=p),p)
            bad=deepcopy(p);bad['files'][p['account_review_path']]+=b' '
            with self.assertRaises(ValueError):other.read({'state':state},frozen_package=bad)
            clock[0]+=timedelta(seconds=120)
            with self.assertRaises(ValueError):provider.read({'state':state})
    def test_known_dividend_and_receipt_request_tamper(self):
        state,clock,calls,source=fixture(self.args);request=review_request(state)
        p=source({k:request[k] for k in ('account_id','state_revision','window_start','observed_floor','securities','current_target_quantities')})
        from hashlib import sha256
        for mode in ('dividend','period'):
            bad=deepcopy(p);rp=bad['documents']['action_receipts']['A'];r=json.loads(bad['files'][rp])
            if mode=='dividend':
                rawpath=r['raw_path'];obj=json.loads(bad['files'][rawpath]);obj['chart']['result'][0]['events']={'dividends':{'x':{'date':int(clock[0].timestamp()),'amount':1}}}
                bad['files'][rawpath]=json.dumps(obj).encode();bad['source_hashes'][rawpath]=sha256(bad['files'][rawpath]).hexdigest();r['raw_sha256']=bad['source_hashes'][rawpath]
            else:r['request_period1']+=100
            bad['files'][rp]=json.dumps(r).encode();bad['source_hashes'][rp]=sha256(bad['files'][rp]).hexdigest()
            with self.assertRaises(ValueError):derive_paper_review(state,None,bad,clock[0])
    def test_explicit_ancestor_future_reject_and_original_genesis_events(self):
        from hashlib import sha256
        from data.current_quantity_v2_paper_ledger import digest
        from test_current_quantity_v2_paper_chain import ready
        state,clock,calls,source=fixture(self.args)
        # Already-recorded fills can reside inside genesis, before chain creation.
        from data.current_quantity_v2_paper_chain import create_chain
        compact=create_chain(state['ledger'])
        self.assertEqual(review_request(compact)['securities'].keys(),{'A','B'})
        legacy,_=ready();clock[0]=datetime.fromisoformat(legacy['ledger']['last_recorded_at'])
        def baseline(at):
            r=dict(schema='EXPLICIT_PAPER_RIGHTS_BASELINE_V1',account_id=legacy['ledger']['account_id'],state_revision=legacy['ledger']['revision'],
                chain_sha256=digest(legacy),pending_rights=[],reviewed_at=at.isoformat(),source_references=['baseline/evidence'])
            files={'baseline/chain':json.dumps(legacy).encode(),'baseline/review':json.dumps(r).encode(),'baseline/evidence':b'explicit synthetic review'}
            return dict(files=files,source_hashes={p:sha256(v).hexdigest() for p,v in files.items()},documents={'chain':'baseline/chain','review':'baseline/review'})
        b=baseline(clock[0]);request=review_request(legacy,b)
        action=source({k:request[k] for k in ('account_id','state_revision','window_start','observed_floor','securities','current_target_quantities')})
        r=derive_paper_review(legacy,b,action,clock[0]);self.assertEqual(validate_paper_review(r,legacy,clock[0]),r)
        with self.assertRaises(ValueError):derive_paper_review(legacy,baseline(clock[0]+timedelta(seconds=1)),action,clock[0])

    def test_failed_save_never_publishes(self):
        state,clock,calls,source=fixture(self.args)
        with TemporaryDirectory() as folder:
            p=DerivedPaperReviewProvider(storage_root=folder,evidence_reader=source,clock=lambda:clock[0])
            with patch('data.current_quantity_v2_paper_review_provider._publish',side_effect=OSError('disk')):
                with self.assertRaises(OSError):p.capture({'state':state})
            with self.assertRaises(ValueError):p.read({'state':state})

if __name__=='__main__':unittest.main()

