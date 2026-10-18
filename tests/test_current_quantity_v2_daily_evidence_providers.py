import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from hashlib import sha256

from backtest.current_quantity_v2_daily_evidence_providers import DailyEvidenceProviders
from backtest.current_quantity_v2_daily_simulation import run_daily
from backtest.current_quantity_v2_simulated_settlement import _references
from data.current_quantity_v2_late_unit_review import BoundedLateUnitReview,STATUS
from data.current_quantity_v2_paper_action_sources import PaperActionEvidenceSources
from data.current_quantity_v2_simulation_origin_files import SimulationOriginFilesReader
import test_current_quantity_v2_daily_simulation as daily_fixture
import test_current_quantity_v2_current_cash_plan as cash_fixture
from test_current_quantity_v2_current_cash_ledger import frozen_fixture


class DailyProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cash_fixture.CurrentCashTests.setUpClass()
    @classmethod
    def tearDownClass(cls):cash_fixture.CurrentCashTests.tearDownClass()

    def bundle(self,folder,*,candidate=False):
        args,captures,quotes,clock=daily_fixture.DailySimulationTests.arguments(self,folder)
        state=args['store'].read(args['simulation_id'])['simulation']
        config=args['continuation_arguments'](state,args['session'])
        schedule_path=Path(config['root'])/config['schedule_path']
        schedule=json.loads(schedule_path.read_bytes())
        schedule['sessions'].insert(0,dict(date='2026-10-15',open_at='2026-10-15T09:30:00-04:00',close_at='2026-10-15T16:00:00-04:00'))
        schedule_path.write_text(json.dumps(schedule));config['schedule_sha256']=sha256(schedule_path.read_bytes()).hexdigest()
        args['continuation_arguments']=lambda *_:config
        minute=args['capture_arguments'](state,'2026-10-15')['fetch']
        action_calls=[]
        def daily(ticker,start,end):
            action_calls.append(ticker)
            events={'splits':{'event':{'date':1}}} if candidate else {}
            return dict(status=200,body=json.dumps(dict(chart=dict(error=None,result=[dict(
                meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY'),events=events)]))).encode())
        rss=b'<rss><channel><title>Nasdaq</title><item><title>Unrelated notice</title><pubDate>Fri, 16 Oct 2026 13:00:00 GMT</pubDate></item></channel></rss>'
        source=PaperActionEvidenceSources(fetch=daily,rss_fetch=lambda:dict(status=200,body=rss),clock=args['clock'])
        review=BoundedLateUnitReview(action_sources=source,clock=args['clock'])
        bundle=DailyEvidenceProviders(store=args['store'],root=config['root'],schedule_path=config['schedule_path'],
            schedule_sha256=config['schedule_sha256'],evidence_directory=Path(folder)/'evidence',
            fee_provider=lambda simulation,day:{oid:'0' for oid in simulation['chain']['ledger']['orders']},
            origin_files_reader=SimulationOriginFilesReader(),
            clock=args['clock'],minute_fetch=minute,late_review=review)
        args.update(capture_arguments=bundle.capture_arguments,settlement_review=bundle.settlement_review,close_arguments=bundle.close_arguments)
        return args,bundle,captures,quotes,action_calls

    def test_real_bundle_settle_close_and_no_repeated_transport_on_retry(self):
        with TemporaryDirectory() as folder:
            args,bundle,minutes,quotes,actions=self.bundle(folder)
            self.assertEqual((minutes,quotes,actions),([],[],[]))
            original=args['store'].read(args['simulation_id'])['simulation']
            result=run_daily(**args)
            self.assertEqual(result['daily_status'],'CONTINUATION_COMPLETE')
            self.assertEqual(result['simulation']['valuation']['records'][0]['status'],'COMPLETE')
            self.assertEqual(len(minutes),2);self.assertEqual(len(actions),2)
            self.assertEqual(len(quotes),2)
            for path in (Path(folder)/'evidence').glob('*/close/bounded-review-ready.json'):
                saved=json.loads(path.read_bytes())
                for name in saved['unit_reviews'].values():
                    self.assertEqual(json.loads((path.parent/name).read_bytes())['status'],STATUS)
            self.assertEqual(run_daily(**args)['daily_status'],'ALREADY_COMPLETED')
            self.assertEqual((len(minutes),len(actions),len(quotes)),(2,2,2))
            request_path=next((Path(folder)/'evidence').glob('*/settlement/request.json'))
            prepared=dict(directory=str(request_path.parent),request=json.loads(request_path.read_bytes()))
            # A new instance replays the frozen review archive, with no action IO.
            fresh=DailyEvidenceProviders(store=bundle.store,root=bundle.root,schedule_path=bundle.schedule_path,
                schedule_sha256=bundle.schedule_sha256,evidence_directory=bundle.directory,
                fee_provider=bundle.fee_provider,origin_files_reader=SimulationOriginFilesReader(),
                clock=bundle.clock,minute_fetch=bundle.minute_fetch,late_review=bundle.late_review)
            fresh.settlement_review(original,prepared)
            self.assertEqual(len(actions),2)

    def test_review_failure_keeps_capture_and_cannot_refetch_actions(self):
        with TemporaryDirectory() as folder:
            args,bundle,minutes,quotes,actions=self.bundle(folder,candidate=True)
            before=args['store'].read(args['simulation_id'])
            with self.assertRaisesRegex(ValueError,'LATE_UNIT_CHANGE_CANDIDATE'):run_daily(**args)
            self.assertEqual(args['store'].read(args['simulation_id']),before)
            self.assertEqual(len(minutes),2);self.assertEqual(len(actions),1)
            failure=next((Path(folder)/'evidence').glob('*/settlement/bounded-review-failure.json'))
            saved=json.loads(failure.read_bytes())
            self.assertEqual(saved['reason'],'LATE_UNIT_CHANGE_CANDIDATE')
            self.assertFalse(saved['failed_action_raw_archived']);self.assertIsNotNone(saved['failed_at'])
            with self.assertRaisesRegex(ValueError,'REVIEW_ARCHIVE_INCOMPLETE_NO_RETRY'):run_daily(**args)
            self.assertEqual((len(minutes),len(actions),len(quotes)),(2,1,0))
            self.assertEqual(json.loads(failure.read_bytes()),saved)


if __name__=='__main__':unittest.main()
