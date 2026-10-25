from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch
from contextlib import nullcontext
from data.strategy_account_evidence_provider import StrategyAccountEvidenceProvider

from core.strategy_account_ledger import canonical
from data.strategy_paper_execution_preview_v1 import _local_import_closure
from scripts.run_prospective_paper_v2 import load_runner,SOURCE
from test_strategy_prospective_paper_daily_capture_v2 import arguments
from test_strategy_paper_execution_preview_v1 import capture
from data.strategy_halt_gap_diagnostic_v1 import SOURCE_URL


def configured(folder,monthly=False,extra_sources=None):
    root=Path(folder);review=b'temporary synthetic review'
    release=canonical(dict(schema='PAPER_CAP_EXIT_DAILY_RELEASE_V2',policy_id='MONTHLY_CAP50_EXIT20',
        approved=True,scope='PAPER_DAILY_SIGNAL_RULE_ONLY',approved_at='2026-11-03T14:58:00+00:00'))
    args,_=arguments(folder,extra_code_paths=_local_import_closure({SOURCE}),
        integration_review_sha256=sha256(review).hexdigest(),extra_sources={**(extra_sources or {}),'policy/cap.json':release})
    authority=args['authority'];source=authority['descriptor_arguments']
    def write(path,raw):
        destination=root/path;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(raw)
        return dict(path=path,sha256=sha256(raw).hexdigest())
    for path,raw in (source['code_bytes']|source['source_bytes']).items():write(path,raw)
    identity=write('runtime/identity-source',b'identity B')
    manifest=canonical(dict(candidates=[dict(ticker='B',security_id='B',status='READY_CONDITIONAL',
        identity_reviewed=True,identity_source_references=[identity['path']])],source_hashes={identity['path']:identity['sha256']}))
    unit=json.loads(args['selection_arguments']['source_package']['files']['review.paper.json'])
    training={k:unit[k] for k in ('training_manifest_sha256','historical_search_arguments_sha256','training_closed_at')}
    training['historical_price_basis']=unit['securities']['B']['historical_price_basis']
    config=dict(schema='REGISTERED_PROSPECTIVE_PAPER_RUNTIME_V2',
        descriptor=write('runtime/descriptor.json',source['descriptor_bytes']),
        approval=write('runtime/approval.json',source['approval_bytes']),calendar=write('runtime/calendar.json',source['calendar_bytes']),
        registration=write('runtime/registration.json',authority['registration_bytes']),
        integration_review=write('runtime/review.txt',review),daily_release_path='policy/daily.json',cap_release_path='policy/cap.json',
        daily_sources={'B':dict(configuration=write('runtime/daily.json',args['capture_requests']['B']['configuration_bytes']),
            parent=args['capture_requests']['B']['parent_reference'])},identity_manifest=write('runtime/identity.json',manifest),
        securities={'B':{'ticker':'B'}},training_context=training)
    if monthly:
        package=args['selection_arguments']['source_package']
        for path,raw in package['files'].items():write(path,raw)
        # Historical training has its own calendar.json. Keep the registered
        # future execution calendar at a separate immutable fixture path.
        daily=json.loads(args['capture_requests']['B']['configuration_bytes'])
        daily['calendar']=config['calendar']
        config['daily_sources']['B']['configuration']=write('runtime/daily.json',canonical(daily))
        name=args['selection_arguments']['manifest_path']
        config['selection_training_manifest']=dict(path=name,sha256=package['source_hashes'][name])
    reference=write('runtime/config.json',canonical(config))
    return dict(root=root,configuration_path=reference['path'],expected_sha256=reference['sha256'],
                clock=lambda:datetime.fromisoformat('2026-11-03T15:00:00+00:00'))


class RuntimeInitializationTests(unittest.TestCase):
    def test_first_window_template_needs_no_fake_parent(self):
        with TemporaryDirectory() as folder:
            args=configured(folder)
            root=Path(folder);path=root/args['configuration_path'];config=json.loads(path.read_bytes())
            item=config['daily_sources']['B'];daily_path=root/item['configuration']['path']
            daily=json.loads(daily_path.read_bytes())
            daily.update(schema='PAPER_FIRST_DAILY_WINDOW_V2',security_id='B',identity=daily.pop('identity_review'))
            daily.pop('security');item.pop('parent')
            raw=canonical(daily);daily_path.write_bytes(raw);item['configuration']['sha256']=sha256(raw).hexdigest()
            raw=canonical(config);path.write_bytes(raw);args['expected_sha256']=sha256(raw).hexdigest()
            runner=load_runner(**args,initialize=True)
            self.assertNotIn('parent_reference',runner.daily_context.templates['B'])
            self.assertTrue(callable(runner.daily_context.snapshot_reader))

    def test_configured_monthly_capture_selects_and_publishes_once(self):
        self.exercise_monthly_route()

    def test_registry_training_route_publishes_using_loaded_provider(self):
        self.exercise_monthly_route(registry=True)

    def test_registered_publication_policy_route_publishes_using_loaded_provider(self):
        self.exercise_monthly_route(registry=True,policy=True)

    def test_first_month_seed_publishes_without_waiting_for_future_policy(self):
        self.exercise_monthly_route(registry=True,policy=True,seed=True)

    def exercise_monthly_route(self,registry=False,policy=False,seed=False):
        with TemporaryDirectory() as folder:
            route_raw=canonical(dict(schema='bridge-seam-only'))
            args=configured(folder,monthly=True,extra_sources={'runtime/registry.json':route_raw} if policy else None)
            now=['2026-11-03T15:00:00+00:00'];clock=lambda:datetime.fromisoformat(now[0])
            args['clock']=clock
            initial=load_runner(**args,initialize=True);book=initial.coordinator.read()
            now[0]='2026-11-03T15:00:10+00:00';calls=[]
            def market(ticker):calls.append(ticker);return capture(book,clock())[0]['files'][ticker+'.raw']
            def halt():return dict(url=SOURCE_URL,status=200,body=capture(book,clock())[0]['files']['halt.raw'])
            def actions(ticker,start,end):return dict(status=200,body=canonical(dict(chart=dict(error=None,result=[dict(
                meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY'),events={})]))))
            rss=b'<rss><channel><title>Nasdaq</title><pubDate>Tue, 03 Nov 2026 14:00:00 GMT</pubDate><item><title>Unrelated notice</title><pubDate>Tue, 03 Nov 2026 14:00:00 GMT</pubDate></item></channel></rss>'
            bridge=nullcontext()
            if registry:
                # The real publication reader has its own producer integration test.
                # Here substitute only its result, keeping capture and selection real.
                root=Path(folder);config=json.loads((root/args['configuration_path']).read_bytes())
                reference=config.pop('selection_training_manifest')
                if seed:config['selection_training_manifest']=reference
                descriptor=json.loads((root/config['descriptor']['path']).read_bytes())
                provider=StrategyAccountEvidenceProvider(root=root,manifest_path=reference['path'],
                    manifest_sha256=reference['sha256'],training_closed_at=config['training_context']['training_closed_at'],
                    market_capture=None,action_capture=None,limits_builder=None,output_root=root/'unused',
                    runtime_pins=descriptor['code_sha256'],clock=clock)
                raw=canonical(dict(schema='bridge-seam-only'))
                (root/'runtime/registry.json').write_bytes(raw)
                config['selection_monthly_policy' if policy else 'selection_monthly_registry']=dict(path='runtime/registry.json',sha256=sha256(raw).hexdigest())
                raw=canonical(config);(root/args['configuration_path']).write_bytes(raw);args['expected_sha256']=sha256(raw).hexdigest()
                bridge=patch('scripts.run_prospective_paper_v2.'+('load_published_month' if policy else 'load_monthly_training'),return_value=dict(
                    provider=provider,securities={'B':{'ticker':'B'}},training_context=config['training_context']))
            runtime=load_runner(**args,transports=dict(market_fetch=market,halt_fetch=halt,action_fetch=actions,
                rss_fetch=lambda:dict(status=200,body=rss)))
            with bridge as mocked:
                result=runtime.publish_monthly()
                if registry:
                    if seed:mocked.assert_not_called()
                    else:mocked.assert_called_once()
            self.assertEqual(result['status'],'MONTHLY_TARGET_PUBLISHED')
            self.assertEqual(runtime.coordinator.current_target_id(),result['target_id'])
            self.assertEqual(runtime.publish_monthly()['status'],'MONTHLY_TARGET_ALREADY_PUBLISHED')
            self.assertEqual(calls,['B'])
            self.assertEqual(runtime.coordinator.read(),book)

    def test_configuration_initializes_then_reopens_without_duplicate_cash(self):
        with TemporaryDirectory() as folder:
            args=configured(folder)
            runner=load_runner(**args,initialize=True)
            book=runner.coordinator.read()
            self.assertEqual(book['cash'],'20000')
            self.assertEqual(book['orders'],{})
            self.assertEqual(runner.run_once()['status'],'WAIT_MONTHLY_TARGET')
            self.assertEqual(load_runner(**args).coordinator.read(),book)
            self.assertEqual(load_runner(**args,initialize=True).coordinator.read(),book)

    def test_invalid_source_fails_before_any_initialization(self):
        for file in ('runtime/daily.json','runtime/identity-source'):
            with self.subTest(file=file),TemporaryDirectory() as folder:
                args=configured(folder);(Path(folder)/file).write_bytes(b'changed')
                with self.assertRaises(ValueError):load_runner(**args,initialize=True)
                self.assertFalse((Path(folder)/'data/current_strategy_paper').exists())


if __name__=='__main__':unittest.main()
