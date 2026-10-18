import json,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from hashlib import sha256
from datetime import datetime
from test_monthly_automatic_review_request import automatic_fixture
from test_current_quantity_v2_monthly_known_source_review import evidence
from scripts.collect_monthly_automatic_review_evidence import collect
from scripts.coordinate_monthly_simulation import run
from data.current_quantity_v2_source_admission_policy import SOURCE_WITHDRAWALS


def fixture(folder):
    root,args,calls,daily,inputs,save=automatic_fixture(folder)
    # Synthetic fixture builders intentionally share root helper files. Re-pin a
    # separate synthetic descriptor to those actual bytes, never a production source.
    settings=json.loads((root/'settings.json').read_bytes());settings['fixed_source_hashes']['synthetic-evidence.json']=sha256((root/'synthetic-evidence.json').read_bytes()).hexdigest()
    coordinator=json.loads((root/'coordinator.json').read_bytes());coordinator['settings_sha256']=save('settings.json',settings);args['config_sha256']=save('coordinator.json',coordinator)
    initial=json.loads((root/'config.json').read_bytes());descriptor=json.loads((root/initial['descriptor']['path']).read_bytes())
    descriptor['source_hashes']={p:sha256((root/p).read_bytes()).hexdigest() for p in descriptor['source_hashes']}
    initial['descriptor']=dict(path='collector-descriptor.json',sha256=save('collector-descriptor.json',descriptor))
    bootstrap_sha=save('collector-bootstrap.json',initial)
    for record in SOURCE_WITHDRAWALS:
        for p,h in record['evidence'].items():
            target=root/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(Path(p).read_bytes())
    seen=[]
    def rss():seen.append('RSS');return dict(status=200,body=evidence()['feed_raw'])
    kwargs=dict(coordinator_config=root/'coordinator.json',coordinator_sha256=args['config_sha256'],bootstrap_config=root/'collector-bootstrap.json',bootstrap_sha256=bootstrap_sha,policy_path='auto-policy.json',policy_sha256=sha256((root/'auto-policy.json').read_bytes()).hexdigest(),output_directory='collected',clock=args['clock'],rss_fetch=rss)
    return root,args,calls,daily,kwargs,seen


class CollectorTests(unittest.TestCase):
    def test_complete_real_synthetic_collector_into_coordinator_and_reuse(self):
        with TemporaryDirectory() as d:
            root,args,calls,daily,kw,seen=fixture(d);db=Path(daily['database_path']);before=db.read_bytes()
            self.assertEqual(collect(**kw)['status'],'PREFLIGHT_ONLY');self.assertEqual(seen,[])
            self.assertEqual(collect(**kw,execute=True)['status'],'WAITING_TRAINING_CAPTURE');self.assertFalse((root/'collected').exists())
            manual={k:v for k,v in args.items() if not k.startswith('auto_review_')}
            self.assertEqual(run(**manual,execute=True)['status'],'WAITING_REVIEW')
            result=collect(**kw,execute=True);self.assertEqual(result['status'],'EVIDENCE_READY',result)
            self.assertEqual(collect(**kw,execute=True),result);self.assertEqual(seen,['RSS'])
            result=run(**manual,execute=True,auto_review_inputs=result['inputs_path'],auto_review_inputs_sha256=result['inputs_sha256'])
            self.assertEqual(result['status'],'MONTHLY_RUNTIME_PUBLISHED',result);self.assertEqual(len(calls),1);self.assertEqual(db.read_bytes(),before)

    def test_actual_outside_held_capture_late_review_and_publish(self):
        from test_current_quantity_v2_simulated_settlement import evidence_for
        from backtest.current_quantity_v2_simulated_settlement import settle,_references
        from backtest.current_quantity_v2_simulation_store import SimulationStore
        with TemporaryDirectory() as d:
            root,args,calls,daily,kw,seen=fixture(d);store=SimulationStore(daily['database_path']);saved=store.read(daily['simulation_id'])
            ev,through=evidence_for(saved['simulation']['chain'],_references(saved['simulation']['chain']))
            store.apply(simulation_id=daily['simulation_id'],expected_revision=saved['revision'],operation_id='fill-before-collect',request={'kind':'TEST_FILL'},transform=lambda state:settle(simulation=state,evidence=ev,observed_through=through,evaluated_at=through))
            before=Path(daily['database_path']).read_bytes();manual={k:v for k,v in args.items() if not k.startswith('auto_review_')}
            self.assertEqual(run(**manual,execute=True)['status'],'WAITING_REVIEW')
            def close(url,**kwargs):seen.append('CLOSE');return dict(raw=(root/'new-held.json').read_bytes(),http_status=200,final_url=url,response_headers={})
            def action(ticker,start,end):seen.append('ACTION');return dict(status=200,body=json.dumps(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY'),events={})]))).encode())
            kw.update(close_fetch=close,action_fetch=action)
            result=collect(**kw,execute=True);self.assertEqual(result['status'],'EVIDENCE_READY',result)
            self.assertEqual(collect(**kw,execute=True),result);self.assertEqual(seen,['RSS','CLOSE','ACTION','RSS'])
            generated=json.loads((root/result['inputs_path']).read_bytes());self.assertEqual(set(generated['held_bar_sources']),{'A'})
            self.assertEqual(run(**manual,execute=True,auto_review_inputs=result['inputs_path'],auto_review_inputs_sha256=result['inputs_sha256'])['status'],'MONTHLY_RUNTIME_PUBLISHED')
            self.assertEqual(Path(daily['database_path']).read_bytes(),before)

    def test_real_pipeline_wrapper_all_stages_with_only_transport_injection(self):
        from unittest.mock import patch
        from scripts.run_monthly_simulation_pipeline import run as pipeline
        with TemporaryDirectory() as d:
            root,args,calls,daily,kw,seen=fixture(d);before=Path(daily['database_path']).read_bytes()
            inputs={k:v for k,v in kw.items() if k!='rss_fetch'}
            # Delegate unchanged real stages; inject only synthetic HTTP transports.
            with patch('scripts.run_monthly_simulation_pipeline.coordinate',side_effect=lambda **values:run(**values,fetch=args['fetch'])),patch('scripts.run_monthly_simulation_pipeline.collect',side_effect=lambda **values:collect(**values,rss_fetch=kw['rss_fetch'])):
                result=pipeline(**inputs,execute=True);self.assertEqual(result['status'],'MONTHLY_RUNTIME_PUBLISHED')
                self.assertEqual(pipeline(**inputs,execute=True),result)
            self.assertEqual(len(calls),1);self.assertEqual(seen,['RSS']);self.assertEqual(Path(daily['database_path']).read_bytes(),before)

    def test_beforeclose_missing_account_and_failed_transport_no_retry(self):
        with TemporaryDirectory() as d:
            root,args,calls,daily,kw,seen=fixture(d)
            early=dict(kw,clock=lambda:datetime.fromisoformat('2026-11-02T20:00:00+00:00'))
            self.assertEqual(collect(**early,execute=True)['status'],'WAITING_SESSION_CLOSE');self.assertEqual(seen,[])
            Path(daily['database_path']).unlink();self.assertEqual(collect(**kw,execute=True)['status'],'WAITING_ACCOUNT');self.assertEqual(seen,[])
        with TemporaryDirectory() as d:
            root,args,calls,daily,kw,seen=fixture(d);run(**{k:v for k,v in args.items() if not k.startswith('auto_review_')},execute=True)
            def fail():seen.append('FAIL');raise OSError('synthetic transport failure')
            kw['rss_fetch']=fail
            with self.assertRaises(ValueError):collect(**kw,execute=True)
            with self.assertRaisesRegex(ValueError,'NO_RETRY'):collect(**kw,execute=True)
            self.assertEqual(seen,['FAIL']);self.assertTrue((root/'collected/failed.json').exists());self.assertTrue((root/'collected/official-feed/receipt.json').exists())

if __name__=='__main__':unittest.main()
