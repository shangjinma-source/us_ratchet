from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from data.registered_quantity_v2_paper_protocol import *

def fixture(root):
    root=Path(root)
    def save(name,value):
        path=root/name;path.write_text(json.dumps(value),encoding='utf8')
        return dict(path=name,sha256=sha256(path.read_bytes()).hexdigest())
    calendar=save('calendar.json',dict(calendar=['2099-01-05','2099-01-06'],sessions=[dict(date=d,open_at=d+'T09:30:00-05:00',close_at=d+'T16:00:00-05:00') for d in ['2099-01-05','2099-01-06']],source_hashes={}))
    fees=save('fees.json',dict(schema='EXPLICIT_SIMULATION_FEE_MODEL_V1',status='MODELLED_FEES_NOT_BROKER_FEES',fixed_per_order='0',notional_rate='0'))
    protocol=save('protocol.json',dict(description='synthetic explicitly approved operational protocol'))
    identity=dict(account_id='acct',simulation_id='sim',database_path=str(root/'paper.sqlite3'),initial_cash='20000',currency='USD')
    evaluation=dict(start_session='2099-01-05',end_session='2099-01-06')
    bootstrap=save('bootstrap.json',dict(root=str(root),database_path=identity['database_path'],simulation_id='sim',account_id='acct',initial_cash='20000',model='STRICT_CROSS_FULL_FILL_AT_LIMIT',schedule=calendar,fees=fees,pullback={'policy':'synthetic'}))
    daily=save('daily.json',dict(root=str(root),database_path=identity['database_path'],simulation_id='sim',schedule_path=calendar['path'],schedule_sha256=calendar['sha256'],fees_path=fees['path'],fees_sha256=fees['sha256'],pullback={'policy':'synthetic'},monthly=None,monthly_blob_root=None))
    auth=save('auth.json',dict(registration_id='test',authorized=True,identity=identity,evaluation=evaluation,protocol_sha256=protocol['sha256']))
    calauth=save('calauth.json',dict(registration_id='test',authorized=True,calendar_sha256=calendar['sha256']))
    request=dict(schema='REGISTERED_PAPER_REQUEST_V1',registration_id='test',output_directory='registration',identity=identity,evaluation=evaluation,refs=dict(protocol=protocol,authorization=auth,bootstrap=bootstrap,daily=daily,calendar=calendar,calendar_authorization=calauth),source_hashes={fees['path']:fees['sha256']},external_flow_policy='FORBID',calendar_policy='EXPLICIT_AUTHORIZED_CONDITIONAL')
    ref=save('request.json',request)
    args=dict(root=root,request_path=root/'request.json',expected_request_sha256=ref['sha256'],now=datetime.fromisoformat('2099-01-04T10:00:00-05:00'))
    return args,request,save

class ProtocolTests(unittest.TestCase):
    def test_create_runtime_end_and_decision_windows(self):
        with TemporaryDirectory() as folder:
            args,request,save=fixture(folder)
            result=validate_registration_request(**args)
            receipt=dict(schema='REGISTERED_PAPER_RECEIPT_V1',request_sha256=args['expected_request_sha256'],registered_at=args['now'].isoformat())
            args['now']=datetime.fromisoformat('2099-01-07T10:00:00-05:00')
            result=validate_registration(**args,receipt=receipt)
            with self.assertRaisesRegex(ValueError,'OUTSIDE_EVALUATION'):validate_decision_time(validated=result,now=args['now'])
            with self.assertRaisesRegex(ValueError,'BACKFILL'):validate_registration_request(**args)
            self.assertFalse(Path(result['database_path']).exists())

    def test_external_digest_and_pin_conflicts(self):
        with TemporaryDirectory() as folder:
            args,request,save=fixture(folder)
            args['expected_request_sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'REQUEST_HASH'):validate_registration_request(**args)
            request['source_hashes']['fees.json']='0'*64
            args['expected_request_sha256']=save('request.json',request)['sha256']
            with self.assertRaisesRegex(ValueError,'CONFLICTING'):validate_registration_request(**args)

    def test_source_evidence_is_hash_checked_not_parsed_as_json(self):
        with TemporaryDirectory() as folder:
            args,request,save=fixture(folder)
            source=Path(folder)/'source.py';source.write_text('VERSION = 1\n')
            evidence=dict(path='source.py',sha256=sha256(source.read_bytes()).hexdigest(),lines=[1])
            request['refs']['protocol']=save('protocol.json',dict(evidence=[evidence]))
            auth=json.loads((Path(folder)/'auth.json').read_bytes());auth['protocol_sha256']=request['refs']['protocol']['sha256']
            request['refs']['authorization']=save('auth.json',auth)
            args['expected_request_sha256']=save('request.json',request)['sha256']
            validate_registration_request(**args)
            source.write_text('VERSION = 2\n')
            with self.assertRaisesRegex(ValueError,'SOURCE_HASH_MISMATCH'):validate_registration_request(**args)

    def test_database_and_sidecar_prevent_adoption(self):
        for suffix in ('','-wal','-shm','-journal'):
            with self.subTest(suffix=suffix),TemporaryDirectory() as folder:
                args,request,save=fixture(folder)
                Path(request['identity']['database_path']+suffix).write_bytes(b'existing')
                with self.assertRaisesRegex(ValueError,'DATABASE_EXISTS'):validate_registration_request(**args)

    def test_configuration_and_authority_drift(self):
        for mode in ('account','calendar','authorization','flow'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                args,request,save=fixture(folder)
                if mode=='flow':request['external_flow_policy']='ALLOW'
                else:
                    key={'account':'bootstrap','calendar':'calendar','authorization':'authorization'}[mode]
                    obj=json.loads((Path(folder)/request['refs'][key]['path']).read_text())
                    if mode=='account':obj['account_id']='other'
                    if mode=='calendar':obj['sessions'][0]['close_at']='2099-01-06T16:00:00-05:00'
                    if mode=='authorization':obj['authorized']=False
                    request['refs'][key]=save(request['refs'][key]['path'],obj)
                args['expected_request_sha256']=save('request.json',request)['sha256']
                with self.assertRaises(ValueError):validate_registration_request(**args)


class ProtocolStoreTests(unittest.TestCase):
    def prepare(self,folder):
        from test_bootstrap_current_quantity_v2_simulation import fixture as boot_fixture,fetch,NOW
        from scripts.bootstrap_current_quantity_v2_simulation import run
        from backtest.current_quantity_v2_simulation_store import SimulationStore
        bootroot=Path(folder)/'bootstrap-fixture';bootroot.mkdir()
        config,bootargs=boot_fixture(bootroot)
        observed=datetime.fromisoformat('2026-10-15T10:00:30-04:00')
        def transport(ticker):
            raw=json.loads(fetch(ticker));chart=raw['chart']['result'][0]
            chart['meta']['regularMarketTime']-=7200
            chart['timestamp']=[t for t in chart['timestamp'] if t<int(observed.timestamp())//60*60]
            n=len(chart['timestamp']);chart['indicators']['quote']=[{k:v[:n] for k,v in chart['indicators']['quote'][0].items()}]
            return json.dumps(raw).encode()
        run(**bootargs,execute=True,clock=lambda:observed,fetch=transport)
        store=SimulationStore(config['database_path'])
        state=store.read(config['simulation_id'])['simulation']
        final={'store':store}
        args,request,save=fixture(folder)
        origin=state['origin']['ledger'];started=stamp(origin['acceptance']['accepted_at'])
        day=started.astimezone(NY).date().isoformat()
        request['identity'].update(account_id=origin['account_id'],simulation_id=state['simulation_id'],initial_cash=origin['cash'],database_path=str(final['store'].path))
        request['evaluation']=dict(start_session=day,end_session=day)
        dates=state['valuation']['registration']['calendar']['session_dates']
        request['refs']['calendar']=save('schedule.json',dict(calendar=dates,sessions=[dict(date=d,open_at=d+'T09:30:00-04:00',close_at=d+'T16:00:00-04:00') for d in dates]))
        for key in ('bootstrap','daily'):
            config=json.loads((Path(folder)/(key+'.json')).read_text())
            config.update(database_path=str(final['store'].path),simulation_id=state['simulation_id'])
            if key=='bootstrap':config.update(account_id=origin['account_id'],initial_cash=origin['cash'],schedule=request['refs']['calendar'])
            else:config.update(schedule_path='schedule.json',schedule_sha256=request['refs']['calendar']['sha256'])
            request['refs'][key]=save(key+'.json',config)
        request['refs']['authorization']=save('auth.json',dict(registration_id='test',authorized=True,identity=request['identity'],evaluation=request['evaluation'],protocol_sha256=request['refs']['protocol']['sha256']))
        request['refs']['calendar_authorization']=save('calauth.json',dict(registration_id='test',authorized=True,calendar_sha256=request['refs']['calendar']['sha256']))
        args['expected_request_sha256']=save('request.json',request)['sha256'];args['now']=started
        registered=started.replace(day=started.day-1)
        receipt=dict(schema='REGISTERED_PAPER_RECEIPT_V1',request_sha256=args['expected_request_sha256'],registered_at=registered.isoformat())
        validated=validate_registration(**args,receipt=receipt)
        start=dict(schema='REGISTERED_PAPER_START_V1',request_sha256=args['expected_request_sha256'],started_at=started.isoformat(),origin_sha256=digest(state['origin']))
        return validated,start,state,started,save,final['store']

    def test_real_store_start_and_external_cash_mutation_rejected(self):
        with TemporaryDirectory() as folder:
            validated,start,state,now,save,store=self.prepare(folder)
            before=store.path.read_bytes()
            self.assertEqual(validate_start_receipt(validated=validated,receipt=start,simulation=state,now=now)['status'],'START_AND_REPLAY_BOUND')
            changed=deepcopy(state);changed['chain']['ledger']['cash']='999999'
            with self.assertRaises(ValueError):validate_start_receipt(validated=validated,receipt=start,simulation=changed,now=now)
            foreign=deepcopy(validated);foreign['request']['identity']['account_id']='foreign'
            with self.assertRaises(ValueError):validate_start_receipt(validated=foreign,receipt=start,simulation=state,now=now)
            start['started_at']=now.replace(day=now.day+1).isoformat()
            with self.assertRaises(ValueError):validate_start_receipt(validated=validated,receipt=start,simulation=state,now=now)
            self.assertEqual(store.path.read_bytes(),before)

    def test_route_only_month_fields_can_change_and_bound_hash(self):
        with TemporaryDirectory() as folder:
            validated,start,state,now,save,store=self.prepare(folder)
            month=validated['request']['evaluation']['start_session'][:7]
            manifest=save('manifest.json',dict(decision_date=month+'-01'))
            calendar=save('month-calendar.json',dict(target_month=month,decision_date=month+'-01'))
            identities=save('identities.json',{})
            monthly=save('month.json',dict(schema='QUANTITY_V2_MONTHLY_SERVER_INPUTS_V2',market_entries=[dict(target_month=month,decision_date=month+'-01',source_hashes={r['path']:r['sha256'] for r in [manifest,calendar,identities]},manifest_path=manifest['path'],calendar_path=calendar['path'],identities_path=identities['path'],held_bar_sources={})],account_reviews=[]))
            config=dict(validated['documents']['daily'],monthly=monthly,monthly_blob_root=str(Path(folder)/'blobs'))
            route=dict(schema='REGISTERED_PAPER_ROUTE_V1',request_sha256=validated['request_sha256'],identity=validated['request']['identity'],target_month=month,configuration=save('candidate.json',config))
            ref=save('route.json',route)
            args=dict(validated=validated,route_path='route.json',expected_route_sha256=ref['sha256'],simulation=state)
            self.assertEqual(validate_route_binding(**args)['status'],'ROUTE_BOUND')
            config['database_path']=str(Path(folder)/'other.sqlite3');route['configuration']=save('candidate.json',config)
            with self.assertRaisesRegex(ValueError,'ROUTE_CONFIG_HASH'):validate_route_binding(**args)
            args['expected_route_sha256']=save('route.json',route)['sha256']
            with self.assertRaisesRegex(ValueError,'FIXED_CONFIG'):validate_route_binding(**args)


    def test_post_end_real_continuation_is_not_admitted_but_settlement_is(self):
        from test_current_quantity_v2_continuation_simulation import expire_all,daily_arguments,cash_review
        from backtest.current_quantity_v2_continuation_simulation import apply_continuation
        with TemporaryDirectory() as folder:
            validated,start,state,now,save,store=self.prepare(folder)
            expired=expire_all(state)
            later=stamp('2026-10-16T10:00:30-04:00')
            self.assertEqual(validate_start_receipt(validated=validated,receipt=start,simulation=expired,now=later)['status'],'START_AND_REPLAY_BOUND')
            args,_,_=daily_arguments(folder,expired,'2026-10-16')
            args.update(root=Path(folder)/'bootstrap-fixture',unit_review_reader=cash_review)
            from data.current_quantity_v2_pullback_runtime import LazyPullbackCapStore
            boot=json.loads((args['root']/'config.json').read_bytes())
            original_fetch=args['fetch']
            def complete_minutes(ticker):
                raw=json.loads(original_fetch(ticker));chart=raw['chart']['result'][0]
                chart['timestamp']=list(range(chart['meta']['currentTradingPeriod']['regular']['start'],int(args['clock']().timestamp())//60*60,60))
                n=len(chart['timestamp']);chart['indicators']['quote']=[{k:[v[0]]*n for k,v in chart['indicators']['quote'][0].items()}]
                return json.dumps(raw).encode()
            args['fetch']=complete_minutes
            args['pullback_policy']=boot['pullback']['policy']
            args['pullback_cap_store']=LazyPullbackCapStore(boot['pullback']['database_path'],clock=lambda:args['clock']().isoformat(),max_history_rows=512,max_history_bytes=128*1024*1024)
            (args['root']/'daily-schedule.json').write_bytes((Path(folder)/'daily-schedule.json').read_bytes())
            accepted=apply_continuation(**args)['simulation']
            with self.assertRaisesRegex(ValueError,'OUTSIDE_EVALUATION_DECISION_PERIOD'):
                validate_start_receipt(validated=validated,receipt=start,simulation=accepted,now=stamp('2026-10-16T10:01:00-04:00'))

    def test_calendar_model_and_fees_are_runtime_bindings(self):
        from test_current_quantity_v2_continuation_simulation import expire_all
        with TemporaryDirectory() as folder:
            validated,start,state,now,save,store=self.prepare(folder)
            for mode in ('calendar','close','model'):
                changed=deepcopy(validated)
                if mode=='calendar':changed['calendar']['calendar']=changed['calendar']['calendar'][:1]
                elif mode=='close':changed['calendar']['sessions'][0]['close_at']='2026-10-15T15:59:00-04:00'
                else:changed['documents']['bootstrap']['model']='OTHER'
                with self.subTest(mode=mode),self.assertRaises(ValueError):
                    validate_start_receipt(validated=changed,receipt=start,simulation=state,now=now)
            expired=expire_all(state)
            fees=save('fees.json',dict(schema='EXPLICIT_SIMULATION_FEE_MODEL_V1',status='MODELLED_FEES_NOT_BROKER_FEES',fixed_per_order='1',notional_rate='0'))
            changed=deepcopy(validated);changed['documents']['daily']['fees_sha256']=fees['sha256']
            with self.assertRaisesRegex(ValueError,'SETTLEMENT_FEE_POLICY_MISMATCH'):
                validate_start_receipt(validated=changed,receipt=start,simulation=expired,now=stamp('2026-10-16T10:00:30-04:00'))


if __name__=='__main__':unittest.main()
