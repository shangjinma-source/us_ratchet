import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime, timezone
import unittest
from core.strategy_account_ledger import replay
from data.strategy_monthly_supplement_capture import capture_supplement
from data.monthly_peak_raw_history import review_monthly_supplement as strict_review
from test_monthly_peak_raw_history import MonthlyRawHistoryTests

path=Path(__file__).resolve().parents[1]/'data/frontier_monthly_peak_raw_history_v1.py'
spec=importlib.util.spec_from_file_location('frontier_monthly_candidate',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class MonthlyScopedTests(unittest.TestCase):
    def fixture(self,folder,mutation=None):
        inputs,series=MonthlyRawHistoryTests().fixture()
        now=datetime(2026,10,6,14,tzinfo=timezone.utc)
        state=replay('test',[])
        binding=dict(target_id='target',account_id='test',account_revision=state['revision'],session='2026-10-06')
        request=dict(account_id='test',state_revision=state['revision'],window_start='2026-10-01T13:30:00+00:00',observed_floor=now.isoformat(),securities={'A':{'ticker':'TEST'}},current_target_quantities={'A':10})
        from data.saved_frontier_first_window_v1 import VERIFIED_UNRELATED_FUTURE_NOTICES
        v=VERIFIED_UNRELATED_FUTURE_NOTICES['UTP2026-32']
        rss=('<rss><channel><pubDate>Tue, 06 Oct 2026 13:00:00 GMT</pubDate><item><title>'+v[1]+'</title><NewsCategory>'+v[0]+'</NewsCategory><link>http://www.nasdaqtrader.com/TraderNews.aspx?id=UTP2026-32</link><description>'+v[2]+'</description><pubDate>Tue, 27 Oct 2026 19:30:00 GMT</pubDate></item></channel></rss>').encode()
        if mutation=='issuer':rss=rss.replace(b'UTP - SIP',b'UTP - SIP TEST')
        if mutation=='unknown':rss=rss.replace(b'2027 Failover',b'2028 Failover')
        if mutation=='action':series['events']={'dividends':{'1':{'amount':1,'date':1}}}
        capture=capture_supplement(directory=folder,request=request,binding=binding,read_binding=lambda:binding,execute=True,clock=lambda:now,fetch_daily=lambda *a:dict(status=200,body=json.dumps(dict(chart=dict(error=None,result=[series]))).encode()),fetch_official=lambda:dict(status=200,body=rss))
        return dict(capture=capture,request=request,binding=binding,inputs=inputs,identities={'A':dict(ticker='TEST',exchange='NMS')},now=now)
    def test_full_capture_scope_pass_and_legacy_still_strict(self):
        with TemporaryDirectory() as d:
            args=self.fixture(d)
            with self.assertRaisesRegex(ValueError,'SUPPLEMENT_RSS_TIME'):strict_review(**args)
            result=module.review_monthly_supplement(**args)
            self.assertEqual(result['status'],'CONDITIONAL_MONTHLY_SOURCE_REVIEW')
            self.assertEqual(len(result['future_notice_scope']['A']['ignored_future_items']),1)
            self.assertFalse(result['policy_approved'])
    def test_frontier_wrapper_scope_is_bound_into_review_hash(self):
        import sys
        from unittest.mock import patch
        from hashlib import sha256
        from core.strategy_account_ledger import canonical
        wrapper_path=path.parent/'saved_frontier_source_review_v1.py'
        wrapper_spec=importlib.util.spec_from_file_location('frontier_wrapper_candidate',wrapper_path)
        wrapper=importlib.util.module_from_spec(wrapper_spec)
        with patch.dict(sys.modules,{'data.frontier_monthly_peak_raw_history_v1':module}):
            wrapper_spec.loader.exec_module(wrapper)
        with TemporaryDirectory() as d:
            args=self.fixture(d);args['inputs']['base_target']['origin_reference']='proposal'
            state=replay('test',[])
            result=wrapper.review_proposal_monthly_sources(
                target=dict(target_id='target',payload=dict(account_id='test',target_month='2026-10')),
                proposal=dict(proposal_id='proposal',payload=dict(proposed_target_quantities={'A':10})),
                state=state,risk_state=None,inputs=args['inputs'],identities=args['identities'],
                capture=args['capture'],request=args['request'],
                execution_session=dict(date='2026-10-06',open='2026-10-06T13:30:00+00:00',close='2026-10-06T20:00:00+00:00'),now=args['now'])
            self.assertIn('A',result['future_notice_scope'])
            digest=result.pop('review_id');self.assertEqual(digest,sha256(canonical(result)).hexdigest())

    def test_target_and_unknown_future_and_real_chart_action_reject(self):
        for mutation in ('issuer','unknown','action'):
            with self.subTest(mutation=mutation),TemporaryDirectory() as d:
                args=self.fixture(d,mutation)
                with self.assertRaisesRegex(ValueError,'WAIT_KNOWN_ACTION|MONTHLY_RAW_ACTION_REVIEW_REQUIRED'):
                    module.review_monthly_supplement(**args)

if __name__=='__main__':unittest.main()
