from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from core.strategy_account_ledger import canonical
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_prospective_paper_source_capture_v1 import capture_prospective_sources,CODE_PATHS
from data.strategy_halt_gap_diagnostic_v1 import SOURCE_URL
from data.strategy_daily_market_capture_v3 import DailyMarketCaptureV3
from core.strategy_account_ledger import create_account
from test_strategy_prospective_paper_integration_v1 import fixture
from test_strategy_paper_execution_preview_v1 import capture


class SourceCaptureTests(unittest.TestCase):
    def arguments(self,folder):
        root=Path(folder);(root/'fixture').mkdir()
        daily=fixture(root/'fixture',extra_code_paths=CODE_PATHS)
        now=datetime.fromisoformat('2026-11-03T15:00:10+00:00')
        package,_=capture(daily['book'],now)
        identity=b'isolated identity bytes';(root/'identity').write_bytes(identity)
        manifest=canonical(dict(candidates=[dict(ticker='B',security_id='B',status='READY_CONDITIONAL',
            identity_reviewed=True,identity_source_references=['identity'])],source_hashes={'identity':sha256(identity).hexdigest()}))
        (root/'manifest.json').write_bytes(manifest)
        def action(ticker,start,end):return dict(status=200,body=canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY'),events={})]))))
        rss=b'<rss><channel><title>Nasdaq</title><pubDate>Tue, 03 Nov 2026 14:00:00 GMT</pubDate><item><title>Unrelated notice</title><pubDate>Tue, 03 Nov 2026 14:00:00 GMT</pubDate></item></channel></rss>'
        return dict(book=daily['book'],authority=daily['authority'],admitted_decisions={},
            identity_resolver=PinnedStrategyIdentity(root,'manifest.json',sha256(manifest).hexdigest()),
            securities={'B':{'ticker':'B'}},target_quantities={'B':10},window_start='2026-11-02T14:30:00+00:00',
            output_directory=root/'capture',clock=lambda:now,market_fetch=lambda ticker:package['files'][ticker+'.raw'],
            halt_fetch=lambda:dict(url=SOURCE_URL,status=200,body=package['files']['halt.raw']),
            action_fetch=action,rss_fetch=lambda:dict(status=200,body=rss))

    def test_formal_paper_capture_uses_original_transport_and_persists_evidence(self):
        with TemporaryDirectory() as folder:
            args=self.arguments(folder);before=deepcopy(args['book'])
            result=capture_prospective_sources(**args)
            self.assertEqual(result['receipt']['status'],'CAPTURED_NOT_ADMITTED')
            self.assertEqual(args['book'],before)
            self.assertEqual(result['market_capture']['account_revision'],before['revision'])
            mark=result['market_capture']['marks']['B']
            self.assertEqual(len(mark['source_references']),2)
            self.assertIn('transport_timing_reference',mark)
            self.assertTrue((Path(args['output_directory'])/'actions'/'complete-v6.json').is_file())
            self.assertTrue((Path(args['output_directory'])/'market-halts'/'source.raw').is_file())
            with self.assertRaises(FileExistsError):capture_prospective_sources(**args)

    def test_mutated_book_or_missing_identity_rejected_and_failures_preserved(self):
        for mode in ('revision','identity','fetch'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                args=self.arguments(folder)
                if mode=='revision':args['book']['revision']='forged'
                elif mode=='identity':(Path(folder)/'identity').write_bytes(b'changed')
                else:args['market_fetch']=lambda ticker:b'not json'
                with self.assertRaises((ValueError,KeyError)):capture_prospective_sources(**args)
                if mode!='revision':self.assertTrue((Path(args['output_directory'])/'failed.json').is_file())

    def test_same_raw_and_identity_produce_same_v20_mark_fields(self):
        with TemporaryDirectory() as folder:
            args=self.arguments(folder)
            paper=capture_prospective_sources(**args)['market_capture']
            real=DailyMarketCaptureV3(identity_resolver=args['identity_resolver'],fetch=args['market_fetch'],clock=args['clock']).capture(
                state=create_account('comparison-fixture-only'),candidate_metadata=args['securities'],output_directory=Path(folder)/'real-reference')
            left=deepcopy(real['marks']['B']);right=deepcopy(paper['marks']['B'])
            for package,mark in ((real,left),(paper,right)):
                timing=mark.pop('transport_timing_reference')
                self.assertEqual(sha256(package['files'][timing['path']]).hexdigest(),timing['sha256'])
                self.assertFalse(json.loads(package['files'][timing['path']])['raw_modified'])
            self.assertEqual(left,right)
            self.assertEqual(real['identities'],paper['identities'])
            self.assertEqual(real['session'],paper['session'])
            for path in real['marks']['B']['source_references']:
                self.assertEqual(real['files'][path],paper['files'][path])


if __name__=='__main__':unittest.main()
