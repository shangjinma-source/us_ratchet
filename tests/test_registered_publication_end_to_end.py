"""Real registration/bootstrap and monthly pipeline publication; synthetic market only."""
from datetime import datetime,timedelta
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from test_bootstrap_current_quantity_v2_simulation import fixture,fetch
from test_publish_monthly_market_configuration import inputs
from test_monthly_automatic_review_request import automatic_fixture
from scripts import run_registered_quantity_v2_paper_simulation as runtime
from scripts import publish_registered_paper_monthly_route as publisher


def registered_setup(folder):
    root=Path(folder)
    def save(name,value):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
        return dict(path=name,sha256=sha256(path.read_bytes()).hexdigest())
    config,_=fixture(root)
    # The old fixture reuses four filenames for monthly inputs. Preserve genesis
    # under stable paths BEFORE registration; do not patch validation or receipts.
    descriptor=json.loads((root/'descriptor.json').read_bytes())
    mapping={n:'genesis/'+n for n in ('A.json','B.json','input.json','admission.json')}
    for n in ('A.json','B.json'):save(mapping[n],json.loads((root/n).read_bytes()))
    source=json.loads((root/'input.json').read_bytes())
    for row in source['valuation_quotes']:row['source_references']=[mapping.get(v,v) for v in row['source_references']]
    for row in source['bar_sources'].values():row['path']=mapping[row['path']]
    inp=save(mapping['input.json'],source)
    admission=json.loads((root/'admission.json').read_bytes());admission.update(input_path=inp['path'],input_sha256=inp['sha256'])
    save(mapping['admission.json'],admission)
    descriptor['input_path']=mapping['input.json'];descriptor['admission_path']=mapping['admission.json']
    descriptor['source_hashes']={mapping.get(p,p):sha256((root/mapping.get(p,p)).read_bytes()).hexdigest() for p in descriptor['source_hashes']}
    config['descriptor']=save('genesis/descriptor.json',descriptor)
    month=json.loads((root/'month.json').read_bytes());month['original_source_hashes']=descriptor['source_hashes']
    config['initial_month']=save('genesis/month.json',month)
    calendar=json.loads((root/'schedule.json').read_bytes())
    calendar['sessions'] += [dict(date=d,open_at=d+'T09:30:00-05:00',close_at=d+'T16:00:00-05:00') for d in ('2026-11-02','2026-12-01','2026-12-31','2027-01-01')]
    calendar['calendar']=[r['date'] for r in calendar['sessions']]
    evidence=save('genesis/calendar-evidence.json',{'synthetic':True})
    calendar['source_hashes']={evidence['path']:evidence['sha256']}
    config['schedule']=save('registered-calendar.json',calendar)
    boot=save('registered-bootstrap.json',config)
    daily=dict(schema='ISOLATED_V2_DAILY_RUNTIME_V1',root=str(root),database_path=config['database_path'],simulation_id=config['simulation_id'],schedule_path=config['schedule']['path'],schedule_sha256=config['schedule']['sha256'],runtime_directory=str(root/'daily'),fees_path=config['fees']['path'],fees_sha256=config['fees']['sha256'],capture_audit_roots=[config['audit_directory']],monthly_blob_root=None,monthly=None,pullback=config['pullback'])
    daily_ref=save('registered-daily.json',daily)
    identity={k:config[k] for k in ('account_id','simulation_id','database_path','initial_cash')};identity['currency']='USD'
    evaluation=dict(start_session='2026-10-15',end_session='2027-01-01')
    protocol=save('registered-protocol.json',dict(scope='SYNTHETIC_INTEGRATION_NOT_MARKET_CERTIFICATION'))
    refs=dict(protocol=protocol,bootstrap=boot,daily=daily_ref,calendar=config['schedule'],authorization=save('registered-auth.json',dict(registration_id='integration',authorized=True,identity=identity,evaluation=evaluation,protocol_sha256=protocol['sha256'])),calendar_authorization=save('registered-cal-auth.json',dict(registration_id='integration',authorized=True,calendar_sha256=config['schedule']['sha256'])))
    pins={}
    modules={runtime.SELF:runtime,runtime.registrar.CORE:runtime.core,runtime.registrar.REGISTRAR:runtime.registrar,runtime.STORE:runtime.stores,**runtime.EXECUTION_MODULES}
    for n,m in modules.items():
        p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(Path(m.__file__).read_bytes());pins[n]=sha256(p.read_bytes()).hexdigest()
    req=save('registered-request.json',dict(schema='REGISTERED_PAPER_REQUEST_V1',registration_id='integration',output_directory='registration',identity=identity,evaluation=evaluation,refs=refs,source_hashes=pins,external_flow_policy='FORBID',calendar_policy='EXPLICIT_AUTHORIZED_CONDITIONAL'))
    runtime.registrar.run(root=root,request_path=req['path'],expected_request_sha256=req['sha256'],execute=True,clock=lambda:datetime.fromisoformat('2026-10-14T10:00:00-04:00'))
    observed=datetime.fromisoformat('2026-10-15T10:00:30-04:00')
    def quotes(ticker):
        raw=json.loads(fetch(ticker));c=raw['chart']['result'][0];c['meta']['regularMarketTime']-=7200
        c['timestamp']=[t for t in c['timestamp'] if t<int(observed.timestamp())//60*60]
        c['indicators']['quote']=[{k:v[:len(c['timestamp'])] for k,v in c['indicators']['quote'][0].items()}]
        return json.dumps(raw).encode()
    result=runtime.run(root=root,registration_directory='registration',expected_request_sha256=req['sha256'],execute=True,clock=lambda:observed,transports={'quotes':quotes})
    assert result['status']=='REGISTERED_BOOTSTRAP_COMPLETE',result
    # Reuse real monthly preparation fixture; its namespace may now change safely.
    published=publisher.coordinator.publish(**inputs(folder))
    return dict(daily_config=root/daily_ref['path'],daily_sha256=daily_ref['sha256'],monthly_path=published['config_path'],monthly_sha256=published['config_sha256'],session='2026-12-01',monthly_blob_root=str(Path(config['audit_directory'])/'blobs'),output=root/'unused-daily.json'),config


class RegisteredPublicationIntegration(unittest.TestCase):
    def test_real_registration_bootstrap_pipeline_and_publication(self):
        with TemporaryDirectory() as folder:
            with patch('test_monthly_automatic_review_request.account_setup',side_effect=registered_setup):
                root,args,calls,daily,auto,save_hash=automatic_fixture(folder)
            def save(name,value):
                p=root/name;p.write_text(json.dumps(value));return dict(path=name,sha256=sha256(p.read_bytes()).hexdigest())
            req=json.loads((root/'registered-request.json').read_bytes());request_hash=sha256((root/'registered-request.json').read_bytes()).hexdigest()
            settings=json.loads((root/'settings.json').read_bytes());config=json.loads((root/'coordinator.json').read_bytes())
            settings['schedule_path']=req['refs']['calendar']['path'];settings['fixed_source_hashes'].pop('schedule.json',None)
            settings['fixed_source_hashes'][settings['schedule_path']]=req['refs']['calendar']['sha256']
            settings['fixed_source_hashes'].update(json.loads((root/settings['schedule_path']).read_bytes())['source_hashes'])
            config['settings_sha256']=save('settings.json',settings)['sha256'];config['daily_config']=str(root/'registered-daily.json')
            args['config_sha256']=save('coordinator.json',config)['sha256']
            result=publisher.coordinator.run(**args,execute=True)
            self.assertEqual(result['status'],'MONTHLY_RUNTIME_PUBLISHED')
            rolling=save('registered-rolling.json',dict(schema='ROLLING_MONTHLY_SIMULATION_V1',root=str(root),bootstrap=req['refs']['bootstrap'],first_coordinator=dict(path='coordinator.json',sha256=args['config_sha256']),rolling_output_directory='registered-rolling',policy=dict(path='auto-policy.json',sha256=sha256((root/'auto-policy.json').read_bytes()).hexdigest())))
            pins={}
            paths={n:Path(f()) for n,f in publisher.MODULES.items()};paths.update({n:Path(publisher.__file__).resolve().parents[1]/n for n in publisher.COMPILE_SOURCES})
            for n,p in paths.items():
                dest=root/n;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(p.read_bytes());pins[n]=sha256(dest.read_bytes()).hexdigest()
            plan=json.loads((root/settings['plan_path']).read_bytes())
            policy=save('registered-policy.json',dict(schema='REGISTERED_PAPER_MONTHLY_PUBLICATION_POLICY_V1',request_sha256=request_hash,registration_directory='registration',authorization='COMPLETED_PAPER_BIND_ONLY',rolling=rolling,source_hashes=pins,output_directory='registered-routes',domain=dict(path=plan['domain_path'],sha256=plan['domain_source_hashes'][plan['domain_path']]),domain_source_hashes=plan['domain_source_hashes']))
            options=dict(root=root,registration_directory='registration',expected_request_sha256=request_hash,policy_path=policy['path'],expected_policy_sha256=policy['sha256'],target_month=config['session'][:7],clock=args['clock'])
            before=Path(daily['database_path']).read_bytes();captures=len(calls)
            self.assertEqual(publisher.run(**options)['status'],'PREFLIGHT_ONLY')
            done=publisher.run(**options,execute=True);self.assertEqual(done['status'],'POLICY_AUTHORIZED_ROUTE')
            self.assertEqual(publisher.run(**options,execute=True),done)
            self.assertEqual(before,Path(daily['database_path']).read_bytes());self.assertEqual(captures,len(calls))
            validated=runtime.load_bundle(root=root,registration_directory='registration',expected_request_sha256=request_hash,now=args['clock']())
            state=runtime.audit_runtime_receipts(validated=validated,now=args['clock']())['state']
            publisher.core.validate_route_binding(validated=validated,route_path=done['route_path'],expected_route_sha256=done['route_sha256'],simulation=state)
