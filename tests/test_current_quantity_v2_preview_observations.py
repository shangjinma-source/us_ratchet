from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import unittest
import json
import os

from data.current_quantity_v2_preview_observations import ObservedCurrentCashPreview


class PreviewObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = datetime(2026, 10, 15, 15, tzinfo=timezone.utc)
        self.service = Mock()
        self.wrapper = ObservedCurrentCashPreview(service=self.service,
            directory=Path(self.temp.name)/'observations', clock=lambda: self.now)

    def test_constructor_no_write_and_unavailable_is_not_fill_or_old_success(self):
        self.assertFalse(self.wrapper.journal.root.exists())
        self.service.preview.return_value = dict(status='UNAVAILABLE', reason='OUTSIDE_REGULAR_SESSION', orders=[])
        result = self.wrapper.preview('a'*64)
        self.assertEqual(result['observation_record']['status'], 'SAVED')
        self.assertEqual(self.service.preview.call_count, 1)
        history = self.wrapper.history()
        row = history['observations'][0]
        self.assertEqual(row['reason'], 'OUTSIDE_REGULAR_SESSION')
        self.assertEqual(row['orders'], [])
        self.assertFalse(row['actual_fill_inferred'])
        self.assertEqual(row['future_price_evaluation'], 'NOT_EVALUATED')
        self.service.preview.return_value = dict(status='UNAVAILABLE', reason='SECRET_TOKEN_VALUE', orders=[])
        self.now += timedelta(seconds=1)
        self.wrapper.preview('b'*64)
        self.assertEqual(self.wrapper.history(1)['observations'][0]['reason'], 'SOURCE_UNAVAILABLE')
        self.assertEqual(self.wrapper.history(0)['observations'], [])

    def test_chain_budget_and_export_failure_do_not_break_history(self):
        from hashlib import sha256
        self.service.preview.return_value = dict(status='UNAVAILABLE', reason='OUTSIDE_REGULAR_SESSION', orders=[])
        self.wrapper.preview('a'*64)
        payload=b'x'*2048;h=sha256(payload).hexdigest()
        export=dict(files={'pullback-chain/test.json':payload},source_hashes={'pullback-chain/test.json':h},record_paths={'a'*64:dict(path='pullback-chain/test.json',sha256=h)},unavailable=[])
        with patch('data.current_quantity_v2_preview_observations.HISTORY_SOURCE_BUDGET',1024), patch('data.current_quantity_v2_pullback_chain_source.read_pullback_chain_sources',return_value=export), patch('data.current_quantity_v2_touch_review.review_generated_reference',return_value={}) as review:
            result=self.wrapper.history()
            self.assertEqual(result['chain_source_diagnostic'],'CHAIN_SOURCE_BUDGET_OR_COLLISION')
            self.assertNotIn('pullback-chain/test.json',review.call_args.kwargs['files'])
            self.assertEqual(review.call_args.kwargs['trusted_chain_sources'],{})
        with patch('data.current_quantity_v2_pullback_chain_source.read_pullback_chain_sources',side_effect=ValueError('EVENT_BYTE_LIMIT')):
            result=self.wrapper.history();self.assertEqual(result['status'],'OBSERVATION_HISTORY')
            self.assertEqual(result['chain_source_diagnostic'],'CHAIN_SOURCE_UNAVAILABLE_OR_LIMIT')

    def test_logging_failure_is_explicit_and_does_not_modify_valid_orders(self):
        original = dict(status='READY', orders=[dict(security_id='A', quantity=2, limit_price='10')],
            account_id='x', proposal_id='p', reference_valid_until=(self.now+timedelta(seconds=30)).isoformat())
        self.service.preview.return_value = original
        self.wrapper.journal.record = Mock(side_effect=OSError('disk full'))
        result = self.wrapper.preview('a'*64)
        self.assertEqual(result['orders'], original['orders'])
        self.assertEqual(result['observation_record'], {'status':'UNAVAILABLE'})
        self.assertNotIn('observation_record', original)
        self.service.initial_resolver.reset_mock()
        self.service.initial_resolver.return_value = {'accepted':True}
        self.assertEqual(self.wrapper.initial_resolver('x','p',self.now), {'accepted':True})
        self.service.initial_resolver.assert_called_once_with('x','p',self.now)

    def test_expired_during_write_is_not_displayed_as_current(self):
        self.service.preview.return_value = dict(status='READY', account_id='x', proposal_id='p', orders=[{'quantity':2}],
            reference_valid_until=(self.now+timedelta(seconds=2)).isoformat())
        record = self.wrapper.journal.record
        def delayed(*args):
            result = record(*args)
            self.now += timedelta(seconds=3)
            return result
        self.wrapper.journal.record = delayed
        result = self.wrapper.preview('a'*64)
        self.assertEqual(result['reason'], 'REFERENCE_EXPIRED')
        self.assertEqual(result['orders'], [])
        self.assertIsNone(result['proposal_id'])
        self.assertTrue(self.wrapper.history()['observations'][0]['generated_not_confirmed_displayed'])

    def test_new_capture_during_write_removes_old_executable_response(self):
        self.service.preview.return_value = dict(status='READY', account_id='x', proposal_id='p',
            orders=[{'quantity':2}], reference_valid_until=(self.now+timedelta(seconds=30)).isoformat())
        record = self.wrapper.journal.record
        def superseded(*args):
            receipt = record(*args)
            self.service.initial_resolver.side_effect = ValueError('CAPTURE_SUPERSEDED')
            return receipt
        self.wrapper.journal.record = superseded
        result = self.wrapper.preview('a'*64)
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertEqual(result['orders'], [])
        self.assertEqual(self.service.preview.call_count, 1)
        self.assertEqual(self.service.initial_resolver.call_count, 2)
        self.assertEqual(self.wrapper.history()['observations'][0]['status'], 'READY')

    def test_unavailable_observation_binds_exact_cash_research_and_symbols(self):
        self.wrapper.research_context_reader = lambda _: dict(decision_id='a'*64, research_id='a'*24,
            research_version='V2', as_of='2026-10-13', available_cash_exact='20000',
            stocks=[dict(security_id='A', ticker='AAA', ignored='not recorded')])
        self.service.preview.return_value = dict(status='UNAVAILABLE', reason='OUTSIDE_REGULAR_SESSION', orders=[])
        self.wrapper.preview('a'*64)
        context = self.wrapper.history()['observations'][0]['research_context']
        self.assertEqual(context['available_cash_exact'], '20000')
        self.assertEqual(context['stocks'], [{'security_id':'A','ticker':'AAA'}])
        self.now += timedelta(seconds=1)
        self.wrapper.preview('b'*64)
        self.assertIsNone(self.wrapper.history()['observations'][0]['research_context'])

    def test_bound_history_filters_before_limit_and_rejects_missing_context(self):
        version='CURRENT_QUANTITY_V2_FAIR_K_CASH_ONLY_RESEARCH'
        self.wrapper.research_context_reader=lambda decision:dict(decision_id=decision,research_id=decision[:24],research_version=version,as_of='2026-10-13',available_cash_exact='20000',stocks=[])
        self.service.preview.return_value=dict(status='UNAVAILABLE',reason='OUTSIDE_REGULAR_SESSION',orders=[])
        self.wrapper.preview('a'*64)
        for _ in range(3):
            self.now+=timedelta(seconds=1);self.wrapper.preview('b'*64)
        self.wrapper.research_context_reader=None
        self.now+=timedelta(seconds=1);self.wrapper.preview('a'*64)
        bound=dict(decision_id='a'*64,research_version=version,available_cash_exact='20000')
        history=self.wrapper.history(1,**bound)
        self.assertEqual(len(history['observations']),1)
        self.assertEqual(history['observations'][0]['decision_id'],'a'*64)
        self.assertIsNotNone(history['observations'][0]['research_context'])
        self.assertEqual(history['available_cash_exact'],'20000')
        self.assertEqual(self.wrapper.history(50,**dict(bound,available_cash_exact='30000'))['observations'],[])
        self.assertEqual(len(self.wrapper.history()['observations']),5)

    def test_followup_reads_original_bytes_only_for_bound_ready_orders(self):
        binding=dict(decision_id='a'*64,research_version='V2',available_cash_exact='20000')
        event=dict(event_id='c'*32,schema='V2_GENERATED_PREVIEW_OBSERVATION_V1',
            observed_at=self.now.isoformat(),request_started_at=self.now.isoformat(),decision_id=binding['decision_id'],
            research_context=dict(research_id='a'*24,research_version='V2',available_cash_exact='20000'),
            generated_not_confirmed_displayed=True,actual_fill_inferred=False,
            status='READY',orders=[dict(security_id='A')],captures=[])
        self.wrapper.journal.record(event,[])
        original=next((self.wrapper.journal.root/'events').glob('*/*.json')).read_bytes()
        reader=Mock(return_value=dict(binding=binding,status='PENDING_SOURCE_CAPTURE',
            actual_fill_inferred=False,performance_computed=False,orders=[]))
        self.wrapper.followup_reader=reader
        self.wrapper.history()
        self.wrapper.history(**dict(binding,available_cash_exact='30000'))
        reader.assert_not_called()
        result=self.wrapper.history(**binding)
        reader.assert_called_once_with(event_raw=original,binding=binding,now=self.now)
        self.assertEqual(result['observations'][0]['reference_followup']['status'],'PENDING_SOURCE_CAPTURE')
        reader.return_value=dict(binding=dict(binding,available_cash_exact='30000'),
            actual_fill_inferred=False,performance_computed=False)
        self.assertEqual(self.wrapper.history(**binding)['observations'][0]['reference_followup']['status'],'BLOCKED_FOLLOWUP_VALIDATION')
        reader.side_effect=ValueError('PRIVATE_SOURCE_PATH')
        result=self.wrapper.history(**binding)
        self.assertNotIn('PRIVATE_SOURCE_PATH',json.dumps(result))
        self.assertEqual(next((self.wrapper.journal.root/'events').glob('*/*.json')).read_bytes(),original)

    def test_new_date_priority_and_partial_same_day_are_explicit(self):
        root=self.wrapper.journal.root/'events'
        def save(day,number,decision='b'*64,observed=None):
            directory=root/day;directory.mkdir(parents=True,exist_ok=True)
            identifier=f'{number:032x}'
            row=dict(schema='V2_GENERATED_PREVIEW_OBSERVATION_V1',event_id=identifier,
                observed_at=observed or day+'T15:00:00+00:00',decision_id=decision,
                research_context=dict(research_id=decision[:24],research_version='V2',available_cash_exact='20000'),
                captures=[],generated_not_confirmed_displayed=True,actual_fill_inferred=False,
                status='UNAVAILABLE',orders=[])
            path=directory/(identifier+'.json');path.write_text(json.dumps(row));return path
        for number in range(1001):save('2026-10-14',number)
        newest=save('2026-10-15',2000,'a'*64)
        os.utime(newest,(1,1))
        bound=dict(decision_id='a'*64,research_version='V2',available_cash_exact='20000')
        history=self.wrapper.history(**bound)
        self.assertEqual(len(history['observations']),1)
        self.assertTrue(history['scan_limited'])
        self.assertEqual(history['scan_coverage'],'PARTIAL_SCAN')
        self.assertFalse(history['latest_records_guaranteed'])
        self.assertFalse(history['empty_history_proves_no_records'])
        for number in range(3000,4001):save('2026-10-16',number)
        empty=self.wrapper.history(**bound)
        self.assertEqual(empty['observations'],[])
        self.assertEqual(empty['scan_coverage'],'PARTIAL_SCAN')

    def test_partition_hint_is_not_observation_time_authority(self):
        self.service.preview.return_value=dict(status='UNAVAILABLE',orders=[])
        self.wrapper.preview('a'*64)
        self.now+=timedelta(seconds=1);self.wrapper.preview('b'*64)
        root=self.wrapper.journal.root/'events'
        files=list(root.glob('*/*.json'))
        for path in files:
            event=json.loads(path.read_bytes())
            if event['decision_id']=='a'*64:
                target=root/'2026-10-16';target.mkdir();path.rename(target/path.name)
        (root/'not-a-date').mkdir()
        history=self.wrapper.history()
        self.assertEqual([e['decision_id'] for e in history['observations']],['b'*64,'a'*64])
        self.assertEqual(history['rejected_files'],1)
        self.assertEqual(history['scan_coverage'],'PARTIAL_SCAN')

    def test_partition_enumeration_cap_is_partial(self):
        root=self.wrapper.journal.root/'events';root.mkdir(parents=True)
        partition=root/'2026-10-15';partition.mkdir()
        with patch.object(Path,'iterdir',return_value=iter([partition]*4097)):
            history=self.wrapper.history()
        self.assertEqual(history['observations'],[])
        self.assertTrue(history['scan_limited'])
        self.assertEqual(history['scan_coverage'],'PARTIAL_SCAN')

    def test_http_requires_exact_binding(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.current_quantity_v2_difference import create_router
        app=FastAPI();app.include_router(create_router(service=self.wrapper))
        with TestClient(app) as client:
            route='/api/current_portfolio_research/observations'
            self.assertEqual(client.get(route).status_code,400)
            query=dict(decision_id='a'*64,research_version='CURRENT_QUANTITY_V2_FAIR_K_CASH_ONLY_RESEARCH',available_cash_exact='20000')
            response=client.get(route,params=query)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()['decision_id'],'a'*64)
            self.assertEqual(client.get(route,params=dict(query,path='secret')).status_code,400)


class OriginalQuoteEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_current_quantity_v2_current_cash_plan as base
        cls.base = base
        base.CurrentCashTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        cls.base.CurrentCashTests.tearDownClass()

    def test_real_verified_proposal_original_bytes_and_legacy_missing(self):
        import json
        from hashlib import sha256
        from test_current_quantity_v2_current_cash_service import fixture
        with TemporaryDirectory() as folder:
            source, _, supplied, _, clock = fixture(folder, self.base.CurrentCashTests.args)
            wrapper = ObservedCurrentCashPreview(service=source,
                directory=Path(folder)/'observations', clock=lambda: clock[0])
            source.prepare = Mock()
            result = wrapper.preview(supplied['capital_decision']['decision_id'])
            self.assertEqual(result['status'], 'READY')
            source.prepare.assert_called_once()
            event = wrapper.journal.read_event(result['observation_record']['event_path'],
                expected_sha256=result['observation_record']['event_sha256'])
            self.assertEqual(event['source_evidence_status'], 'SAVED_ORIGINAL_QUOTE_BYTES')
            self.assertFalse(event['source_evidence_missing'])
            self.assertEqual(len(event['captures']), 4)
            package = supplied['execution_package']
            for capture in event['captures']:
                original = package['files'][capture['original_source_path']]
                self.assertEqual((wrapper.journal.root/capture['path']).read_bytes(), original)
                self.assertEqual(capture['sha256'], sha256(original).hexdigest())
                self.assertIn(capture['role'], ('ORIGINAL_QUOTE','ORIGINAL_QUOTE_RECEIPT'))
            self.assertEqual(wrapper.history()['rejected_files'], 0)
            self.assertEqual(wrapper.history()['observations'][0]['captures'], event['captures'])
            # Real source bridge reference survives capture-time replay; a later
            # saved observation without a new full minute cannot imply no-touch.
            clock[0] += timedelta(seconds=1)
            later_result=wrapper.preview(supplied['capital_decision']['decision_id'])
            self.assertEqual(later_result['status'],'READY')
            original_row=next(e for e in wrapper.history()['observations'] if e['event_id']==event['event_id'])
            self.assertTrue(original_row['touch_diagnostic']['orders'])
            self.assertTrue(all(o['reason']=='INCOMPLETE_MINUTE_COVERAGE' for o in original_row['touch_diagnostic']['orders']))
            # Summary-only historical records stay missing; no implicit backfill.
            legacy = dict(event, event_id='f'*32)
            legacy.pop('captures');legacy.pop('source_evidence_status');legacy.pop('source_evidence_missing')
            wrapper.journal.record(legacy, [])
            old = next(e for e in wrapper.history()['observations'] if e['event_id']=='f'*32)
            self.assertTrue(old['source_evidence_missing'])
            self.assertEqual(old['source_evidence_status'], 'LEGACY_SOURCE_EVIDENCE_MISSING')

    def test_tampered_frozen_source_not_saved_as_evidence(self):
        from copy import deepcopy
        from test_current_quantity_v2_current_cash_service import fixture
        with TemporaryDirectory() as folder:
            source, _, supplied, _, clock = fixture(folder, self.base.CurrentCashTests.args)
            original = source.initial_resolver
            def damaged(*args):
                value = deepcopy(original(*args))
                package = value['proposal']['causal_inputs']['frozen_execution_package']
                receipt = next(iter(package['documents']['quote_receipts'].values()))
                package['files_base64'][receipt] = 'e30='
                return value
            source.initial_resolver = damaged
            wrapper = ObservedCurrentCashPreview(service=source,
                directory=Path(folder)/'observations', clock=lambda:clock[0])
            wrapper.preview(supplied['capital_decision']['decision_id'])
            event = wrapper.history()['observations'][0]
            self.assertEqual(event['captures'], [])
            self.assertTrue(event['source_evidence_missing'])
            self.assertEqual(event['source_evidence_status'], 'SOURCE_EVIDENCE_UNAVAILABLE')
            self.assertFalse((wrapper.journal.root/'raw').exists())


if __name__ == '__main__': unittest.main()


class TouchHistoryIntegrationTests(unittest.TestCase):
    def test_saved_later_bytes_and_missing_raw(self):
        import json
        from test_current_quantity_v2_touch_review import TouchTests
        args,_,_=TouchTests().fixture(10)
        with TemporaryDirectory() as folder:
            wrapper=ObservedCurrentCashPreview(service=Mock(),directory=folder)
            root=Path(folder)
            for path,raw in args['files'].items():
                if path in ('event','later'):continue
                (root/path).write_bytes(raw)
            for number,key in enumerate(('event','later')):
                value=json.loads(args['files'][key]);identifier=str(number)*32
                for capture in value['captures']:
                    oldpath=capture['path'];capture['path']='raw/'+capture['sha256']+'.bin'
                    (root/'raw').mkdir(exist_ok=True);(root/capture['path']).write_bytes(args['files'][oldpath])
                value.update(event_id=identifier,generated_not_confirmed_displayed=True,actual_fill_inferred=False,future_price_evaluation='NOT_EVALUATED')
                path=root/'events'/'2026-10-15'/(identifier+'.json');path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
            history=wrapper.history()
            original=history['observations'][1]
            self.assertEqual(original['touch_diagnostic']['orders'][0]['status'],'TOUCH_IN_COMPLETE_MINUTE')
            (root/('raw/'+args['source_hashes']['l.raw']+'.bin')).unlink()
            history=wrapper.history()
            self.assertEqual(history['observations'][1]['touch_diagnostic']['orders'][0]['status'],'UNKNOWN')
            self.assertGreater(history['rejected_files'],0)
            (root/'events'/'2026-10-15'/('2'*32+'.json')).write_text('[]')
            bad=dict(value,event_id='3'*32,captures=[None]);(root/'events'/'2026-10-15'/('3'*32+'.json')).write_text(json.dumps(bad))
            self.assertGreaterEqual(wrapper.history()['rejected_files'],3)
