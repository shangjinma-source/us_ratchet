import importlib.util,json,unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock
from data.news_event_pipeline_v1 import EventNewsPipeline
import test_news_sandisk_wire_v1 as fixtures
import test_news_sandisk_wire_capture_v1 as transport

spec=importlib.util.spec_from_file_location('wire_events',Path(__file__).resolve().parents[1]/'docs/candidates/news_event_sources_sandisk_wire.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class WireEventTests(unittest.TestCase):
    def setUp(self):
        f=fixtures.WireTests();f.setUp();self.row=f.row;self.story=f.doc
        self.listing=dict(results=dict(news=[dict(topicstring='SNDK',newsitem=[self.row])]))
        self.now=datetime.fromisoformat('2026-11-04T08:00:00+00:00')
    def test_discover_hydrate_preserves_publication_and_receipts(self):
        with TemporaryDirectory() as folder:
            session=transport.Session([transport.Response(self.listing),transport.Response(self.story)])
            source=module.EventSources(folder,session=session,clock=lambda:self.now)
            row=source.discover('SNDK')[0];event=source.hydrate(row)
            self.assertEqual(event['published_at'],'2026-10-29T20:05:00+00:00')
            self.assertEqual(event['discovered_at'],self.now.isoformat())
            self.assertEqual(source.request_count,2)
            for receipt in source.receipts:
                self.assertTrue((Path(folder)/'raw'/('wire-'+receipt['sha256']+'.json')).is_file())
            with self.assertRaisesRegex(ValueError,'BUDGET_OR_DOMAIN'):
                source.fetch('https://evil.example/',ticker='SNDK')
    def test_old_release_never_inferred_after_source_switch(self):
        for initialized in (False,True):
            with self.subTest(initialized=initialized),TemporaryDirectory() as folder:
                cache=Path(folder);session=transport.Session([transport.Response(self.listing),transport.Response(self.story)])
                context=lambda:(dict(revision='a',shares={'sid':2}),dict(target_id='b',proposal_id='c',payload=dict(target_quantities={'sid':3})),{'sid':'SNDK'})
                service=SimpleNamespace(cache=cache,validate=lambda:None,context=context,bound_context=lambda binding:context(),start_event=Mock(),status=Mock())
                analyzer=Mock();builder=Mock()
                pipeline=EventNewsPipeline(service,sources_factory=lambda *a,**k:module.EventSources(cache,session=session,clock=lambda:self.now),analyzer=analyzer,source_builder=builder,clock=lambda:self.now,
                    calendar_window=lambda stamp:dict(not_before='2026-10-30T13:30:00Z',valid_until='2026-10-30T13:35:00Z'))
                pipeline.set_enabled(True)
                if initialized:
                    state=pipeline.load();state['discovery_initialized_tickers']=['SNDK'];pipeline.save(state)
                pipeline.tick()
                analyzer.assert_not_called();builder.assert_not_called();service.start_event.assert_not_called()
                statuses={entry['status'] for entry in pipeline.load()['seen'].values()}
                self.assertIn('BODY_WINDOW_EXPIRED' if initialized else 'BASELINE_WINDOW_EXPIRED',statuses)

if __name__=='__main__':unittest.main()
