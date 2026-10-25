from datetime import datetime,timedelta
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import test_registered_quantity_v2_paper_protocol as fixtures
from scripts import run_registered_quantity_v2_paper_simulation as runner


def bundle(root,existing=False):
    root=Path(root)
    if existing:
        validated,start,state,now,save,store=fixtures.ProtocolStoreTests().prepare(str(root))
        request=validated['request'];registered=now-timedelta(days=1)
    else:
        args,request,save=fixtures.fixture(root);now=args['now'];registered=now
        start=state=store=None
    for relative,module in [(runner.SELF,Path(runner.__file__)),(runner.registrar.CORE,Path(runner.core.__file__)),
        (runner.registrar.REGISTRAR,Path(runner.registrar.__file__)),(runner.STORE,Path(runner.stores.__file__))]:
        path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(module.read_bytes())
        request['source_hashes'][relative]=sha256(path.read_bytes()).hexdigest()
    request_ref=save('request.json',request);expected=request_ref['sha256']
    output=root/'registration';output.mkdir()
    (output/'request.json').write_bytes((root/'request.json').read_bytes())
    def write(name,value):
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
        return sha256(path.read_bytes()).hexdigest()
    write('started.json',dict(status='STARTED',request_sha256=expected,started_at=registered.isoformat()))
    rh=write('receipt.json',dict(schema='REGISTERED_PAPER_RECEIPT_V1',request_sha256=expected,registered_at=registered.isoformat()))
    write('complete.json',dict(status='REGISTERED_NOT_ACTIVATED',request_sha256=expected,receipt_sha256=rh,completed_at=registered.isoformat()))
    if existing:
        start['request_sha256']=expected
        sh=write('runtime/start.json',start)
        write('runtime/start_complete.json',dict(status='REGISTERED_BOOTSTRAP_COMPLETE',request_sha256=expected,
            registration_receipt_sha256=rh,start_sha256=sh))
    return dict(root=root,registration_directory='registration',expected_request_sha256=expected,clock=lambda:now),request,now,store,save


class RegisteredAdmissionTests(unittest.TestCase):
    def test_receipt_audit_outside_decision_window_is_read_only(self):
        with TemporaryDirectory() as folder:
            args,request,now,store,save=bundle(folder,existing=True)
            observed=now+timedelta(hours=4)
            validated=runner.load_bundle(root=args['root'],registration_directory=args['registration_directory'],
                expected_request_sha256=args['expected_request_sha256'],now=observed)
            database=Path(validated['database_path']);before=database.read_bytes()
            audited=runner.audit_runtime_receipts(validated=validated,now=observed)
            self.assertIsNotNone(audited['state'])
            self.assertIsNotNone(audited['revision'])
            self.assertFalse(audited['account_writes'])
            self.assertEqual(before,database.read_bytes())
            marker=Path(validated['registration_directory'])/'runtime/execution_reconciliation_required.json'
            marker.write_text('{}')
            with self.assertRaisesRegex(ValueError,'RECONCILIATION_REQUIRED'):
                runner.audit_runtime_receipts(validated=validated,now=observed)
            self.assertEqual(before,database.read_bytes())

    def test_registered_bootstrap_real_composition_and_start_receipt(self):
        self.exercise_bootstrap()

    def test_postcommit_result_write_failure_blocks_following_day(self):
        self.exercise_bootstrap(fail_completion=True)

    def test_registered_daily_actual_runtime_without_duplicate_decision(self):
        self.exercise_bootstrap(daily_execute=True)

    def exercise_bootstrap(self,fail_completion=False,daily_execute=False):
        from test_bootstrap_current_quantity_v2_simulation import fixture as boot_fixture,fetch
        with TemporaryDirectory() as folder:
            root=Path(folder);config,_=boot_fixture(root)
            def save(name,value):
                path=root/name;path.write_text(json.dumps(value));return dict(path=name,sha256=sha256(path.read_bytes()).hexdigest())
            calendar=json.loads((root/'schedule.json').read_bytes());calendar['calendar']=[x['date'] for x in calendar['sessions']]
            config['schedule']=save('schedule.json',calendar)
            boot=save('config.json',config)
            daily=dict(schema='ISOLATED_V2_DAILY_RUNTIME_V1',root=str(root),database_path=config['database_path'],simulation_id=config['simulation_id'],
                schedule_path='schedule.json',schedule_sha256=config['schedule']['sha256'],runtime_directory=str(root/'daily'),
                fees_path=config['fees']['path'],fees_sha256=config['fees']['sha256'],capture_audit_roots=[config['audit_directory']],monthly_blob_root=None,monthly=None,pullback=config['pullback'])
            identity=dict(account_id=config['account_id'],simulation_id=config['simulation_id'],database_path=config['database_path'],initial_cash=config['initial_cash'],currency='USD')
            evaluation=dict(start_session='2026-10-15',end_session='2026-10-16')
            protocol=save('protocol.json',dict(description='synthetic approved'))
            request=dict(schema='REGISTERED_PAPER_REQUEST_V1',registration_id='synthetic',output_directory='registration',identity=identity,evaluation=evaluation,
                external_flow_policy='FORBID',calendar_policy='EXPLICIT_AUTHORIZED_CONDITIONAL',source_hashes={},refs=dict(protocol=protocol,bootstrap=boot,daily=save('daily.json',daily),calendar=config['schedule'],
                authorization=save('auth.json',dict(registration_id='synthetic',authorized=True,identity=identity,evaluation=evaluation,protocol_sha256=protocol['sha256'])),
                calendar_authorization=save('calauth.json',dict(registration_id='synthetic',authorized=True,calendar_sha256=config['schedule']['sha256']))))
            modules={runner.SELF:runner,runner.registrar.CORE:runner.core,runner.registrar.REGISTRAR:runner.registrar,runner.STORE:runner.stores,**runner.EXECUTION_MODULES}
            for relative,module in modules.items():
                path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(Path(module.__file__).read_bytes());request['source_hashes'][relative]=sha256(path.read_bytes()).hexdigest()
            ref=save('request.json',request)
            before=datetime.fromisoformat('2026-10-14T10:00:00-04:00')
            runner.registrar.run(root=root,request_path='request.json',expected_request_sha256=ref['sha256'],execute=True,clock=lambda:before)
            observed=datetime.fromisoformat('2026-10-15T10:00:30-04:00')
            def quotes(ticker):
                raw=json.loads(fetch(ticker));chart=raw['chart']['result'][0];chart['meta']['regularMarketTime']-=7200
                chart['timestamp']=[t for t in chart['timestamp'] if t<int(observed.timestamp())//60*60]
                n=len(chart['timestamp']);chart['indicators']['quote']=[{k:v[:n] for k,v in chart['indicators']['quote'][0].items()}]
                return json.dumps(raw).encode()
            args=dict(root=root,registration_directory='registration',expected_request_sha256=ref['sha256'],clock=lambda:observed,transports={'quotes':quotes})
            result=runner.run(**args,execute=True)
            self.assertEqual(result['status'],'REGISTERED_BOOTSTRAP_COMPLETE')
            self.assertTrue((root/'registration/runtime/start_complete.json').exists())
            self.assertEqual(runner.run(**args,execute=True)['status'],'SKIPPED_NO_DISPATCH')
            captures=[]
            def minutes(url):
                from urllib.parse import urlparse
                captures.append(url)
                ticker=urlparse(url).path.rsplit('/',1)[-1]
                raw=json.loads(fetch(ticker));chart=raw['chart']['result'][0]
                chart['timestamp']=chart['timestamp'][:-1]
                chart['indicators']['quote']=[{k:v[:-1] for k,v in chart['indicators']['quote'][0].items()}]
                for key in ('open','high','low','close'):
                    chart['indicators']['quote'][0][key]=[10000]*len(chart['timestamp'])
                return json.dumps(raw).encode()
            def actions(ticker,start,end):
                return dict(status=200,body=json.dumps(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY'),events={})]))).encode())
            if daily_execute:
                def full_minutes(url):
                    from urllib.parse import urlparse
                    captures.append(url)
                    raw=json.loads(fetch(urlparse(url).path.rsplit('/',1)[-1]));chart=raw['chart']['result'][0]
                    regular=chart['meta']['currentTradingPeriod']['regular']
                    chart['timestamp']=list(range(regular['start'],regular['end'],60));n=len(chart['timestamp'])
                    chart['indicators']['quote']=[dict(open=[10000]*n,high=[10000]*n,low=[10000]*n,close=[10000]*n,volume=[10]*n)]
                    return json.dumps(raw).encode()
                def next_quotes(ticker):
                    raw=json.loads(quotes(ticker));chart=raw['chart']['result'][0]
                    chart['timestamp']=[t+86400 for t in chart['timestamp']]
                    chart['meta']['regularMarketTime']+=86400
                    for period in chart['meta']['currentTradingPeriod'].values():
                        period['start']+=86400;period['end']+=86400
                    return json.dumps(raw).encode()
                args['clock']=lambda:datetime.fromisoformat('2026-10-16T10:00:30-04:00')
                args['transports']=dict(minutes=full_minutes,quotes=next_quotes,actions=actions,
                    rss=lambda:dict(status=200,body=b'<rss><channel><title>Nasdaq</title><item><title>Unrelated</title><pubDate>Fri, 16 Oct 2026 13:00:00 GMT</pubDate></item></channel></rss>'))
                result=runner.run(**args,execute=True)
                self.assertEqual(result['daily_status'],'CONTINUATION_COMPLETE')
                self.assertEqual(result['status'],'COMPLETE')
                count=len(captures)
                self.assertTrue(runner.run(**args,execute=True)['replayed'])
                self.assertEqual(len(captures),count)
                return
            args['clock']=lambda:datetime.fromisoformat('2026-10-17T10:00:00-04:00')
            args['transports']=dict(minutes=minutes,actions=actions,rss=lambda:dict(status=200,body=b'<rss><channel><title>Nasdaq</title><item><title>Unrelated</title><pubDate>Sat, 17 Oct 2026 13:00:00 GMT</pubDate></item></channel></rss>'))
            if fail_completion:
                original_save=runner.registrar.save
                store=runner.stores.SimulationStore(config['database_path'])
                previous=store.read(config['simulation_id'])['revision']
                def fail(path,value):
                    if path.name=='result.json' and path.parent.name=='finalize-attempt':raise OSError('synthetic result write failure')
                    return original_save(path,value)
                with patch.object(runner.registrar,'save',side_effect=fail):
                    with self.assertRaises(OSError):runner.run(**args,execute=True)
                self.assertNotEqual(store.read(config['simulation_id'])['revision'],previous)
                self.assertTrue((root/'registration/runtime/execution_reconciliation_required.json').exists())
                count=len(captures)
                args['clock']=lambda:datetime.fromisoformat('2026-10-18T10:00:00-04:00')
                with self.assertRaisesRegex(ValueError,'RECONCILIATION_REQUIRED'):runner.run(**args,execute=True)
                self.assertEqual(len(captures),count)
                return
            terminal=runner.run(**args,execute=True)
            self.assertEqual(terminal['status'],'BLOCKED')
            self.assertEqual(terminal['reason'],'UNKNOWN_UNRESOLVED_ORDERS')
            count=len(captures)
            again=runner.run(**args,execute=True)
            self.assertEqual(again['status'],'BLOCKED');self.assertTrue(again['replayed'])
            self.assertEqual(len(captures),count)

    def test_bundle_waiting_and_shared_lock_no_account_or_dispatch(self):
        with TemporaryDirectory() as root:
            args,request,now,_,_=bundle(root)
            before=sorted(str(p) for p in Path(root).rglob('*'))
            result=runner.run(**args)
            self.assertEqual(result['phase'],'WAITING_FIRST_SESSION')
            self.assertEqual(before,sorted(str(p) for p in Path(root).rglob('*')))
            self.assertEqual(runner.run(**args,verify_under_lock=True)['strategy_dispatches'],0)
            self.assertFalse(Path(request['identity']['database_path']).exists())
            lock=Path(root)/runner.registrar.LOCK;lock.write_bytes(b'other')
            with self.assertRaisesRegex(ValueError,'RUN_LOCK_PRESENT'):runner.run(**args,verify_under_lock=True)
            self.assertEqual(lock.read_bytes(),b'other')

    def test_failed_marker_and_hash_corruption_rejected(self):
        for mode in ('failed.json','lock_cleanup_failed.json','receipt.json'):
            with self.subTest(mode=mode),TemporaryDirectory() as root:
                args,_,_,_,_=bundle(root)
                (Path(root)/'registration'/mode).write_text('{}')
                with self.assertRaises(ValueError):runner.run(**args)

    def test_real_store_requires_matching_start_and_is_never_changed(self):
        with TemporaryDirectory() as root:
            args,_,now,store,_=bundle(root,True)
            before=store.path.read_bytes()
            result=runner.run(**args,verify_under_lock=True)
            self.assertEqual(result['phase'],'BOOTSTRAPPED_CURRENT_SESSION_NO_NEW_DECISION')
            args['clock']=lambda:now+timedelta(hours=8)
            self.assertEqual(runner.run(**args)['phase'],'SETTLEMENT_ONLY_ELIGIBLE_NOT_EXECUTED')
            self.assertEqual(before,store.path.read_bytes())
            (Path(root)/'registration/runtime/start_complete.json').unlink()
            with self.assertRaisesRegex(ValueError,'WITHOUT_REGISTERED_START'):runner.run(**args)
            self.assertEqual(before,store.path.read_bytes())

    def test_no_database_cannot_start_after_approved_first_day(self):
        with TemporaryDirectory() as root:
            args,_,_,_,_=bundle(root)
            args['clock']=lambda:datetime.fromisoformat('2099-01-06T10:00:00-05:00')
            with self.assertRaisesRegex(ValueError,'MISSED_REGISTERED_START'):runner.run(**args)

    def test_hard_interruption_without_failure_marker_blocks_next_day(self):
        with TemporaryDirectory() as root:
            args,_,now,store,_=bundle(root,True)
            path=Path(root)/'registration/runtime/daily-2026-10-15';path.mkdir()
            (path/'started.json').write_text(json.dumps(dict(request_sha256=args['expected_request_sha256'])))
            before=store.path.read_bytes()
            args['clock']=lambda:now+timedelta(days=1)
            with self.assertRaisesRegex(ValueError,'INCOMPLETE_EXECUTION_ATTEMPT'):runner.run(**args,execute=True)
            self.assertEqual(before,store.path.read_bytes())
            self.assertTrue((path/'started.json').exists());self.assertFalse((path/'failed.json').exists())

    def test_external_route_hash_and_current_month_required(self):
        with TemporaryDirectory() as root:
            args,request,now,store,save=bundle(root,True)
            month=request['evaluation']['start_session'][:7]
            base=json.loads((Path(root)/'daily.json').read_bytes())
            manifest=save('manifest.json',dict(decision_date=month+'-01'))
            calendar=save('month-calendar.json',dict(target_month=month,decision_date=month+'-01'))
            identities=save('identities.json',{})
            monthly=save('month.json',dict(schema='QUANTITY_V2_MONTHLY_SERVER_INPUTS_V2',
                market_entries=[dict(target_month=month,decision_date=month+'-01',
                    source_hashes={r['path']:r['sha256'] for r in [manifest,calendar,identities]},
                    manifest_path=manifest['path'],calendar_path=calendar['path'],identities_path=identities['path'],held_bar_sources={})],account_reviews=[]))
            base.update(monthly=monthly,monthly_blob_root=str(Path(root)/'blobs'))
            route=dict(schema='REGISTERED_PAPER_ROUTE_V1',request_sha256=args['expected_request_sha256'],
                identity=request['identity'],target_month=month,configuration=save('monthly_daily.json',base))
            ref=save('route.json',route)
            with self.assertRaisesRegex(ValueError,'EXTERNAL_ROUTE_HASH'):runner.run(**args,route_path='route.json')
            self.assertTrue(runner.run(**args,route_path='route.json',expected_route_sha256=ref['sha256'])['route_validated'])
            args['clock']=lambda:now.replace(month=11)
            with self.assertRaisesRegex(ValueError,'ROUTE_NOT_CURRENT_SESSION_MONTH'):
                runner.run(**args,route_path='route.json',expected_route_sha256=ref['sha256'])


if __name__=='__main__':unittest.main()
