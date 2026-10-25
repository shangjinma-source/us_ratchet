"""Publication mechanics over a real completed paper pipeline.
Registration admission is a fixture seam; paper Store/binder/stage receipts are real.
"""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from test_materialize_monthly_successor import completed_fixture
from scripts import publish_registered_paper_monthly_route as publisher


class PublicationTests(unittest.TestCase):
    def test_real_completed_bind_publishes_once_and_reuses_policy_without_new_hash_approval(self):
        with TemporaryDirectory() as folder:
            from scripts.bootstrap_current_quantity_v2_simulation import run as real_bootstrap
            def extended_bootstrap(**options):
                path=Path(options['config_path']);config=json.loads(path.read_bytes());root_path=path.parent
                schedule_path=root_path/config['schedule']['path'];schedule=json.loads(schedule_path.read_bytes())
                schedule['sessions'].extend(dict(date=d,open_at=d+'T09:30:00-05:00',close_at=d+'T16:00:00-05:00') for d in ('2026-12-31','2027-01-01'))
                schedule_path.write_text(json.dumps(schedule));config['schedule']['sha256']=sha256(schedule_path.read_bytes()).hexdigest()
                path.write_text(json.dumps(config));options['config_sha256']=sha256(path.read_bytes()).hexdigest()
                # setup retains this same config dictionary after calling bootstrap;
                # update the test fixture's parent frame is deliberately avoided.
                return real_bootstrap(**options)
            from test_bind_monthly_simulation_runtime import setup as real_account_setup
            def extended_account_setup(directory):
                with patch('test_bind_monthly_simulation_runtime.bootstrap',side_effect=extended_bootstrap):
                    binding,config=real_account_setup(directory)
                config.update(json.loads((Path(directory)/'config.json').read_bytes()))
                daily_path=Path(binding['daily_config']);daily_config=json.loads(daily_path.read_bytes())
                daily_config['schedule_sha256']=config['schedule']['sha256'];daily_path.write_text(json.dumps(daily_config))
                binding['daily_sha256']=sha256(daily_path.read_bytes()).hexdigest()
                return binding,config
            with patch('test_monthly_automatic_review_request.account_setup',side_effect=extended_account_setup):
                root,previous,calls,daily=completed_fixture(folder)
            def save(path,value):
                target=root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(value));return {'path':path,'sha256':sha256(target.read_bytes()).hexdigest()}
            store=publisher.runtime.stores.SimulationStore(daily['database_path']);saved=store.read(daily['simulation_id']);ledger=saved['simulation']['origin']['ledger']
            config=json.loads((root/'coordinator.json').read_bytes());settings=json.loads((root/'settings.json').read_bytes());plan=json.loads((root/settings['plan_path']).read_bytes())
            request_hash='a'*64;receipt_hash='b'*64
            identity=dict(account_id=ledger['account_id'],simulation_id=daily['simulation_id'],database_path=daily['database_path'],initial_cash=ledger['cash'],currency='USD')
            request=dict(identity=identity,evaluation={'start_session':'2026-10-01','end_session':'2027-01-01'},refs={'daily':{'path':'daily.json','sha256':config['daily_sha256']},'bootstrap':{'path':'bootstrap.json','sha256':'c'*64},'calendar':{'path':settings['schedule_path'],'sha256':settings['fixed_source_hashes'][settings['schedule_path']]}})
            validated=dict(registration_directory=str(root/'registration'),request=request,request_sha256=request_hash,root=str(root),database_path=daily['database_path'],registration_receipt_sha256=receipt_hash,documents={'daily':daily})
            start=save('registration/runtime/start.json',{'fixture':True})
            save('registration/runtime/start_complete.json',dict(status='REGISTERED_BOOTSTRAP_COMPLETE',start_sha256=start['sha256'],request_sha256=request_hash,registration_receipt_sha256=receipt_hash))
            rolling=save('rolling.json',dict(schema='ROLLING_MONTHLY_SIMULATION_V1',root=str(root),bootstrap=request['refs']['bootstrap'],first_coordinator={'path':'coordinator.json','sha256':previous['config_sha256']},rolling_output_directory='rolling',policy={'path':'auto-policy.json','sha256':sha256((root/'auto-policy.json').read_bytes()).hexdigest()}))
            pins={}
            paths={name:Path(where()) for name,where in publisher.MODULES.items()}
            paths.update({name:Path(publisher.__file__).resolve().parents[1]/name for name in publisher.COMPILE_SOURCES})
            for name,path in paths.items():
                target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes());pins[name]=sha256(target.read_bytes()).hexdigest()
            policy=save('policy.json',dict(schema='REGISTERED_PAPER_MONTHLY_PUBLICATION_POLICY_V1',request_sha256=request_hash,registration_directory='registration',authorization='COMPLETED_PAPER_BIND_ONLY',rolling=rolling,source_hashes=pins,output_directory='approved-routes',domain={'path':plan['domain_path'],'sha256':plan['domain_source_hashes'][plan['domain_path']]},domain_source_hashes=plan['domain_source_hashes']))
            args=dict(root=root,registration_directory='registration',expected_request_sha256=request_hash,policy_path='policy.json',expected_policy_sha256=policy['sha256'],target_month=config['session'][:7],clock=previous['clock'])
            before=store.path.read_bytes();count=len(calls)
            with patch.object(publisher.runtime,'load_bundle',return_value=validated),patch.object(publisher.core,'validate_start_receipt',return_value={}):
                self.assertEqual(publisher.run(**args)['status'],'PREFLIGHT_ONLY')
                self.assertFalse((root/'approved-routes').exists())
                ticks=iter([previous['clock'](),previous['clock']()-timedelta(seconds=1)])
                with self.assertRaisesRegex(ValueError,'CLOCK_ROLLBACK'):
                    publisher.run(**dict(args,clock=lambda:next(ticks)))
                original_policy=json.loads((root/'policy.json').read_bytes())
                failure_args=dict(args)
                failure_policy=dict(original_policy,output_directory='failed-routes')
                failure_args['policy_path']='failure-policy.json';failure_args['expected_policy_sha256']=save('failure-policy.json',failure_policy)['sha256']
                real_save=publisher.registrar.save
                def fail_route(path,value):
                    if path.name=='route.json':raise OSError('fixture write failure')
                    return real_save(path,value)
                with patch.object(publisher.registrar,'save',side_effect=fail_route):
                    with self.assertRaises(OSError):publisher.run(**failure_args,execute=True)
                with self.assertRaisesRegex(ValueError,'PARTIAL_REQUIRES_REVIEW'):publisher.run(**failure_args,execute=True)
                cleanup_args=dict(args,policy_path='cleanup-policy.json')
                cleanup_args['expected_policy_sha256']=save('cleanup-policy.json',dict(original_policy,output_directory='cleanup-routes'))['sha256']
                original_unlink=Path.unlink
                def failed_unlink(path,*a,**k):
                    if path==root/publisher.registrar.LOCK:raise OSError('fixture cleanup failure')
                    return original_unlink(path,*a,**k)
                with patch.object(Path,'unlink',new=failed_unlink):
                    with self.assertRaises(OSError):publisher.run(**cleanup_args,execute=True)
                original_unlink(root/publisher.registrar.LOCK)
                with self.assertRaisesRegex(ValueError,'PARTIAL_REQUIRES_REVIEW'):publisher.run(**cleanup_args)
                done=publisher.run(**args,execute=True)
                self.assertEqual(done['status'],'POLICY_AUTHORIZED_ROUTE')
                self.assertEqual(publisher.run(**args,execute=True),done)
                self.assertEqual(store.path.read_bytes(),before);self.assertEqual(len(calls),count)
                # Successful publication can be consumed after its original window.
                later=dict(args,clock=lambda:previous['clock']()+timedelta(days=3))
                self.assertEqual(publisher.run(**later),done)
                successor=publisher.successor.run(previous_coordinator=root/'coordinator.json',previous_sha256=previous['config_sha256'],output_directory='rolling/plans/after-'+config['session'][:7],execute=True,clock=previous['clock'])
                next_args=dict(args,target_month=successor['target_month'])
                with self.assertRaisesRegex(ValueError,'PUBLICATION_PIPELINE_INCOMPLETE'):
                    publisher.run(**next_args)
                # Actually complete the next pipeline with new synthetic transport
                # and receipt dates, retaining every prior capture and receipt.
                from datetime import datetime
                next_clock=lambda:datetime.fromisoformat('2026-12-31T22:00:00+00:00')
                next_config=json.loads(Path(successor['coordinator_path']).read_bytes())
                schedule=json.loads((root/settings['schedule_path']).read_bytes())
                original_fetch=previous['fetch']
                def next_fetch(url,**kw):
                    response=original_fetch(url,**kw);payload=json.loads(response['raw']);chart=payload['chart']['result'][0]
                    for day in schedule['calendar']:
                        at=int(datetime.fromisoformat(day+'T16:00:00-05:00').timestamp())
                        if at>chart['timestamp'][-1] and day<='2026-12-31':
                            chart['timestamp'].append(at)
                            for values in chart['indicators']['quote'][0].values():values.append(values[-1])
                            for indicator in chart['indicators'].get('adjclose',[]):indicator['adjclose'].append(indicator['adjclose'][-1])
                    response['raw']=json.dumps(payload).encode();return response
                old_inputs=json.loads((root/'automatic-inputs.json').read_bytes())
                from test_current_quantity_v2_monthly_known_source_review import evidence
                feed=evidence(date='Thu, 31 Dec 2026 21:30:00 GMT')
                (root/'next-feed.xml').write_bytes(feed['feed_raw'])
                receipt=json.loads(feed['feed_receipt_raw']);receipt.update(request_started_at_utc='2026-12-31T21:59:00+00:00',received_at_utc='2026-12-31T21:59:01+00:00')
                receipt_ref=save('next-feed-receipt.json',receipt)
                inputs=deepcopy(old_inputs);inputs['feed_path']='next-feed.xml';inputs['feed_receipt_path']='next-feed-receipt.json'
                inputs['source_hashes'].pop('feed.xml');inputs['source_hashes'].pop('feed-receipt.json')
                inputs['source_hashes'].update({'next-feed.xml':sha256(feed['feed_raw']).hexdigest(),'next-feed-receipt.json':receipt_ref['sha256']})
                inputs_ref=save('next-inputs.json',inputs)
                completed=publisher.coordinator.run(config_path=Path(successor['coordinator_path']),config_sha256=successor['coordinator_sha256'],execute=True,clock=next_clock,fetch=next_fetch,auto_review_inputs='next-inputs.json',auto_review_inputs_sha256=inputs_ref['sha256'])
                self.assertEqual(completed['status'],'MONTHLY_RUNTIME_PUBLISHED',completed)
                next_done=publisher.run(**dict(next_args,clock=next_clock),execute=True)
                self.assertEqual(next_done['status'],'POLICY_AUTHORIZED_ROUTE')
                self.assertEqual(publisher.run(**dict(next_args,clock=next_clock)),next_done)
                # Real automatic route resolver and registered wrapper lock path;
                # the final economic daily worker alone is stubbed.
                from scripts import run_registered_paper_automation as automation
                request['source_hashes']={}
                for name,module in publisher.runtime.EXECUTION_MODULES.items():
                    request['source_hashes'][name]=sha256(Path(module.__file__).read_bytes()).hexdigest()
                validated['first_decision_at']='2026-10-01T10:00:00-04:00'
                validated['end_close_at']='2027-01-01T16:00:00-05:00'
                validated['calendar']=schedule
                entry_pins={}
                for name,where in automation.REQUIRED.items():
                    target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(Path(where()).read_bytes());entry_pins[name]=sha256(target.read_bytes()).hexdigest()
                descriptor=save('automation.json',dict(schema='REGISTERED_PAPER_AUTOMATION_V1',root=str(root),registration_directory='registration',request_sha256=request_hash,publication_policy=policy,source_hashes=entry_pins,log_directory='automation-logs'))
                def scheduled_monthly(**options):
                    self.assertTrue((root/publisher.registrar.LOCK).exists())
                    options['clock']()
                    return dict(status='WAITING_SESSION_CLOSE',completed_months=[config['session'][:7],successor['target_month']])
                with patch.object(automation.rolling,'run',side_effect=scheduled_monthly):
                    monthly_result=automation.run(descriptor_path=root/'automation.json',expected_descriptor_sha256=descriptor['sha256'],mode='monthly',execute=True,clock=next_clock)
                self.assertEqual(len(monthly_result['registered_routes']),2)
                self.assertFalse((root/publisher.registrar.LOCK).exists())
                # A real later settlement advances the Store revision. Both
                # historical bound routes must remain readable after that change.
                from test_current_quantity_v2_continuation_simulation import expire_all
                advanced=store.apply(simulation_id=daily['simulation_id'],expected_revision=saved['revision'],operation_id='later-settlement',request={'kind':'FIXTURE_SETTLEMENT'},transform=expire_all)
                self.assertNotEqual(advanced['revision'],saved['revision'])
                saved=advanced;before=store.path.read_bytes()
                with patch.object(automation.rolling,'run',side_effect=scheduled_monthly):
                    repeated=automation.run(descriptor_path=root/'automation.json',expected_descriptor_sha256=descriptor['sha256'],mode='monthly',execute=True,clock=next_clock)
                self.assertEqual([r['route_sha256'] for r in repeated['registered_routes']],[r['route_sha256'] for r in monthly_result['registered_routes']])
                with patch.object(publisher.runtime.daily,'run_runtime',return_value={'daily_status':'LATE_NO_NEW_DECISION','revision':saved['revision']}) as worker:
                    automated=automation.run(descriptor_path=root/'automation.json',expected_descriptor_sha256=descriptor['sha256'],mode='daily',execute=True,clock=lambda:datetime.fromisoformat('2027-01-01T10:00:30-05:00'))
                self.assertEqual(automated['status'],'SKIPPED')
                self.assertEqual(worker.call_args.kwargs['config_sha256'],json.loads(Path(next_done['route_path']).read_bytes())['configuration']['sha256'])
                self.assertFalse((root/publisher.registrar.LOCK).exists())

                self.assertEqual(store.path.read_bytes(),before)

                # Daily route input is changed only after the real runtime lock
                # has been acquired. The callback must detect it before work.
                proof=json.loads((Path(next_done['route_path']).parent/'complete.json').read_bytes())
                drift_path=root/next(path for path in proof['input_hashes'] if path.endswith('bind.complete.json'))
                drift_original=drift_path.read_bytes()
                real_save_bytes=publisher.registrar.save_bytes
                def drift_after_lock(path,raw):
                    result=real_save_bytes(path,raw)
                    if Path(path)==root/publisher.registrar.LOCK:
                        self.assertTrue(Path(path).exists())
                        drift_path.write_bytes(drift_original+b' ')
                    return result
                with patch.object(publisher.registrar,'save_bytes',side_effect=drift_after_lock),patch.object(publisher.runtime.daily,'run_runtime',side_effect=AssertionError('must not execute')):
                    with self.assertRaisesRegex(ValueError,'AUTOMATION_ROUTE_INPUT_CHANGED'):
                        automation.run(descriptor_path=root/'automation.json',expected_descriptor_sha256=descriptor['sha256'],mode='daily',execute=True,clock=lambda:datetime.fromisoformat('2027-01-01T10:00:31-05:00'))
                self.assertEqual(store.path.read_bytes(),before)
                drift_path.write_bytes(drift_original)

                (root/'stages/bind.complete.json').write_text('{}')
                with self.assertRaises((ValueError,KeyError)):publisher.run(**args)

if __name__=='__main__':unittest.main()
