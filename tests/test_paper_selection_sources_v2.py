from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from core.strategy_account_ledger import canonical
from data.strategy_account_evidence_provider import StrategyAccountEvidenceProvider
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_halt_gap_diagnostic_v1 import SOURCE_URL
from data.strategy_paper_execution_preview_v1 import _local_import_closure
from data.strategy_prospective_paper_selection_sources_v2 import capture_selection_sources,SOURCE
from data.strategy_prospective_paper_selection_v2 import select_prospective_target
from prospective_paper_v2_fixture import fixture
from test_strategy_paper_execution_preview_v1 import capture


class SelectionSourceTests(unittest.TestCase):
    def test_saved_training_and_actual_capture_modules_feed_selector(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);daily=fixture(folder,extra_code_paths=_local_import_closure({SOURCE,
                'data/strategy_account_evidence_provider.py'}))
            args=daily['selection_arguments'];package=args['source_package'];book=daily['book']
            for name,raw in package['files'].items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            raw=b'synthetic identities';(root/'identities').write_bytes(raw)
            manifest=canonical(dict(candidates=[dict(ticker=s,security_id=s,status='READY_CONDITIONAL',
                identity_reviewed=True,identity_source_references=['identities']) for s in ('A','B')],
                source_hashes={'identities':sha256(raw).hexdigest()}))
            (root/'identity-manifest').write_bytes(manifest)
            identity=PinnedStrategyIdentity(root,'identity-manifest',sha256(manifest).hexdigest())
            unit=json.loads(package['files']['review.paper.json'])
            clock=lambda:datetime.fromisoformat('2026-11-03T15:00:10+00:00')
            provider=StrategyAccountEvidenceProvider(root=root,manifest_path=args['manifest_path'],
                manifest_sha256=package['source_hashes'][args['manifest_path']],training_closed_at=unit['training_closed_at'],
                market_capture=None,action_capture=None,limits_builder=None,output_root=root/'unused',
                runtime_pins=package['source_hashes'],clock=clock)
            observed=[]
            def market(ticker):observed.append(ticker);return capture(book,clock())[0]['files'][ticker+'.raw']
            def halt():return dict(url=SOURCE_URL,status=200,body=capture(book,clock())[0]['files']['halt.raw'])
            def actions(ticker,start,end):return dict(status=200,body=canonical(dict(chart=dict(error=None,result=[dict(
                meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY'),events={})]))))
            rss=b'<rss><channel><title>Nasdaq</title><pubDate>Tue, 03 Nov 2026 14:00:00 GMT</pubDate><item><title>Unrelated notice</title><pubDate>Tue, 03 Nov 2026 14:00:00 GMT</pubDate></item></channel></rss>'
            result=capture_selection_sources(book=book,authority=daily['authority'],admitted_decisions={},admitted_settlements={},
                training_provider=provider,identity_resolver=identity,securities={s:{'ticker':s} for s in ('A','B')},
                output_directory=root/'captured',clock=clock,market_fetch=market,halt_fetch=halt,
                action_fetch=actions,rss_fetch=lambda:dict(status=200,body=rss))
            expected=set(provider.training()[1]['prices'])
            self.assertEqual(set(observed),expected)
            timing=json.loads((root/'captured/selection-timing.json').read_bytes())
            self.assertEqual(timing['candidate_count'],len(expected))
            self.assertEqual(timing['capture_count'],len(expected))
            self.assertEqual(set(timing['stage_seconds']),{'context_seconds','training_seconds',
                'capture_seconds','review_seconds','assembly_seconds','input_validation_seconds'})
            self.assertTrue(all(value>=0 for value in timing['stage_seconds'].values()))
            self.assertGreaterEqual(timing['total_seconds'],sum(timing['stage_seconds'].values()))
            self.assertFalse(timing['optimizer_measured'])
            self.assertFalse(any('selection-timing' in path for path in result['source_package']['files']))
            marks=json.loads(result['source_package']['files'][result['marks_path']])
            self.assertEqual(set(marks),expected)
            selected=select_prospective_target(book=book,authority=daily['authority'],admitted_decisions={},
                admitted_settlements={},now=clock().isoformat(),clock=clock,**result)
            self.assertEqual(selected['status'],'TARGET_READY')
            self.assertEqual(book['orders'],{})


if __name__=='__main__':unittest.main()
