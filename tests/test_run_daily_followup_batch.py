import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime
from unittest.mock import patch
from scripts import run_daily_followup_batch as module
from scripts import capture_followup_evidence as capture_module
import test_capture_followup_evidence as fixtures


class DurableBatchTests(unittest.TestCase):
    def test_real_dispatch_capture_duplicate_and_readonly(self):
        fixture=fixtures.CaptureTests();self.addCleanup(fixture.doCleanups)
        with TemporaryDirectory() as folder:
            args,ticks,calls,_=fixture.fixture(folder);root=Path(folder)
            event_path=next((root/'data/quantity_v2_observations/events').rglob('*.json'))
            event=json.loads(event_path.read_bytes());event['status']='READY'
            event_path.write_bytes(capture_module.canonical(event))
            def single(**kw):
                return capture_module.run(**kw,fetch=args['fetch'],action_fetch=args['action_fetch'],rss_fetch=args['rss_fetch'])
            kw=dict(root=root,clock=lambda:ticks[0],single_event=single)
            self.assertEqual(module.run(**kw)['status'],'READ_ONLY')
            self.assertFalse((root/module.STATE_ROOT).exists());self.assertEqual(calls,[])
            first=module.run(**kw,execute=True)
            self.assertEqual(first['status'],'CYCLE_COMPLETE');self.assertEqual(calls,['close','action','rss'])
            second=module.run(**kw,execute=True)
            self.assertEqual(second['state_after']['cycles'],2);self.assertEqual(len(calls),3)
            self.assertEqual(second['pages'][0]['counts']['already_covered'],1)
            self.assertEqual(len(list((root/module.STATE_ROOT/'runs').glob('*/complete.json'))),2)

    def test_cursor_page_resume_recovery_skip_and_cycle_reset(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);directory=root/'data/quantity_v2_observations/events/2026-10-15';directory.mkdir(parents=True)
            for n in range(3):
                event=dict(status='READY',decision_id='a'*64,observed_at='2026-10-15T14:00:0%d+00:00'%n,research_context=dict(research_version='CURRENT_QUANTITY_V2_FAIR_K_CASH_ONLY_RESEARCH',research_id='a'*24,available_cash_exact='20000'))
                (directory/('%032x.json'%n)).write_text(json.dumps(event))
            completed=set();calls=[]
            def single(**kw):
                n=int(kw['event_id'],16)
                if n==0:return dict(status='NEEDS_RECOVERY',reason='PRIOR_CAPTURE_FAILED_REQUIRES_REVIEW')
                if n in completed:return dict(status='ALREADY_COVERED')
                if not kw['execute']:return dict(status='PREFLIGHT_ONLY')
                calls.append(n);completed.add(n);return dict(status='FOLLOWUP_PUBLISHED')
            kw=dict(root=root,clock=lambda:datetime.fromisoformat('2026-10-16T22:00:00+00:00'),single_event=single,max_scan=2,max_dispatch=1)
            first=module.run(**kw,execute=True);self.assertEqual(calls,[1]);self.assertIsNotNone(first['state_after']['cursor'])
            second=module.run(**kw,execute=True);self.assertEqual(calls,[1,2]);self.assertIsNone(second['state_after']['cursor'])
            module.run(**kw,execute=True);self.assertEqual(calls,[1,2])
            # Finish the bounded cycle, then a wider page has two due records.
            module.run(**kw,execute=True)
            completed.clear();calls.clear()
            wider=dict(kw,max_scan=3)
            deferred=module.run(**wider,execute=True)
            self.assertTrue(deferred['pages'][0]['repeat_current_page']);self.assertIsNone(deferred['state_after']['cursor'])
            self.assertEqual(calls,[1]);module.run(**wider,execute=True);self.assertEqual(calls,[1,2])
            lock=root/module.STATE_ROOT/'run.lock';lock.write_bytes(b'other')
            self.assertEqual(module.run(**kw,execute=True)['status'],'NEEDS_RECOVERY');self.assertEqual(lock.read_bytes(),b'other')

    def test_failed_runner_preserves_started_no_retry(self):
        with TemporaryDirectory() as folder:
            kw=dict(root=folder,execute=True)
            with patch.object(module,'dispatch',side_effect=ValueError('SIMULATED_FAILURE')) as dispatcher:
                with self.assertRaisesRegex(ValueError,'SIMULATED_FAILURE'):module.run(**kw)
                self.assertEqual(module.run(**kw)['status'],'NEEDS_RECOVERY');self.assertEqual(dispatcher.call_count,1)
            directory=Path(folder)/module.STATE_ROOT
            self.assertFalse((directory/'state.json').exists());self.assertTrue((directory/'active.json').exists())
            self.assertEqual(len(list((directory/'runs').glob('*/failed.json'))),1)


if __name__=='__main__':unittest.main()
