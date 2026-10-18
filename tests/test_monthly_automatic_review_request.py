import json,unittest
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from test_bind_monthly_simulation_runtime import setup as account_setup
from test_coordinate_monthly_simulation import setup
from test_current_quantity_v2_monthly_known_source_review import evidence,POLICY_SCHEMA
from scripts.coordinate_monthly_simulation import run
from backtest.current_quantity_v2_simulation_store import SimulationStore


def automatic_fixture(folder):
    binding,account=account_setup(folder);daily_raw=Path(binding['daily_config']).read_bytes()
    (Path(folder)/'training').rename(Path(folder)/'original-training')
    root,settings,request,args,calls,save=setup(folder)
    settings['publish_output']='auto-published';config=json.loads((root/'coordinator.json').read_bytes());config['settings_sha256']=save('settings.json',settings)
    (root/'daily.json').write_bytes(daily_raw);config['daily_sha256']=sha256(daily_raw).hexdigest();config['monthly_blob_root']=binding['monthly_blob_root'];args['config_sha256']=save('coordinator.json',config)
    original=args['fetch']
    def fetch(url,**kw):
        result=original(url,**kw);obj=json.loads(result['raw']);obj['chart']['result'][0]['meta']['longName']='Beta Business Corporation';result['raw']=json.dumps(obj).encode();return result
    args['fetch']=fetch
    prior=json.loads((root/'previous.json').read_bytes());member=prior['candidates'][0]
    source='synthetic-class-source.json';h=save(source,dict(synthetic=True))
    row=dict(security_id=member['security_id'],ticker=member['ticker'],issuer_id=member['issuer_id'],status='READY_CONDITIONAL_IDENTITY',identity_reviewed=True,no_unresolved_identifier_conflict=True,unresolved=[],security_class='Synthetic common shares',source_references=[source])
    ch=save('auto-class.json',dict(rows=[row],source_hashes={source:h}))
    candidate=dict(member,status='READY_CONDITIONAL',identity_reviewed=True,identity_source_references=['auto-class.json',source])
    mh=save('auto-identities.json',dict(candidates=[candidate]))
    feed=evidence();(root/'feed.xml').write_bytes(feed['feed_raw']);(root/'feed-receipt.json').write_bytes(feed['feed_receipt_raw'])
    policy=dict(schema=POLICY_SCHEMA,authority='RESEARCH_BOUNDED_SOURCE_ASSUMPTION',maximum_capture_age_seconds=3600,matching='ALL_VISIBLE_ITEMS_EXACT_TICKER_OR_META_NAME',coverage='INCOMPLETE_MAY_OMIT_ACTIONS',retention='UNKNOWN')
    save('auto-policy.json',policy)
    paths=['synthetic-evidence.json',source,'auto-class.json','auto-identities.json','feed.xml','feed-receipt.json','auto-policy.json']
    daily=json.loads(daily_raw);saved=SimulationStore(daily['database_path']).read(daily['simulation_id'])
    inputs=dict(schema='MONTHLY_AUTOMATIC_REVIEW_INPUTS_V1',expected_revision=saved['revision'],source_hashes={p:sha256((root/p).read_bytes()).hexdigest() for p in paths},feed_path='feed.xml',feed_receipt_path='feed-receipt.json',policy_path='auto-policy.json',identity_manifest_path='auto-identities.json',held_bar_sources={})
    args.update(auto_review_inputs='automatic-inputs.json',auto_review_inputs_sha256=save('automatic-inputs.json',inputs))
    return root,args,calls,daily,inputs,save


class AutomaticRequestTests(unittest.TestCase):
    def test_actual_capture_review_publish_bind_and_retry_without_account_writes(self):
        with TemporaryDirectory() as d:
            root,args,calls,daily,inputs,save=automatic_fixture(d);db=Path(daily['database_path']);before=db.read_bytes()
            result=run(**args,execute=True)
            self.assertEqual(result['status'],'MONTHLY_RUNTIME_PUBLISHED',result)
            self.assertEqual(db.read_bytes(),before);self.assertEqual(len(calls),1)
            self.assertEqual(run(**args,execute=True),result);self.assertEqual(len(calls),1)
            request=json.loads((root/'request.json').read_bytes());self.assertEqual(request['held_bar_sources'],{})
            self.assertIn('automatic-review-',request['review_path'])

    def test_notice_and_missing_identity_pause_without_request(self):
        for mode in ('notice','identity'):
            with self.subTest(mode=mode),TemporaryDirectory() as d:
                root,args,calls,daily,inputs,save=automatic_fixture(d)
                if mode=='notice':
                    f=evidence('BBB stock split');(root/'feed.xml').write_bytes(f['feed_raw']);(root/'feed-receipt.json').write_bytes(f['feed_receipt_raw'])
                    for p in ('feed.xml','feed-receipt.json'):inputs['source_hashes'][p]=sha256((root/p).read_bytes()).hexdigest()
                else:inputs['source_hashes'].pop('auto-class.json')
                args['auto_review_inputs_sha256']=save('automatic-inputs.json',inputs)
                result=run(**args,execute=True);self.assertEqual(result['status'],'WAITING_REVIEW',result);self.assertFalse((root/'request.json').exists());self.assertFalse((root/'releases').exists())
                run(**args,execute=True);self.assertEqual(len(calls),1)

    def test_new_evidence_attempt_preserves_unresolved_and_reuses_capture(self):
        with TemporaryDirectory() as d:
            root,args,calls,daily,inputs,save=automatic_fixture(d)
            f=evidence('BBB split candidate');(root/'feed.xml').write_bytes(f['feed_raw']);(root/'feed-receipt.json').write_bytes(f['feed_receipt_raw'])
            for p in ('feed.xml','feed-receipt.json'):inputs['source_hashes'][p]=sha256((root/p).read_bytes()).hexdigest()
            args['auto_review_inputs_sha256']=save('automatic-inputs.json',inputs)
            first=run(**args,execute=True);self.assertEqual(first['status'],'WAITING_REVIEW')
            old_dir=root/'stages'/('automatic-review-'+args['auto_review_inputs_sha256']);old={p:p.read_bytes() for p in old_dir.rglob('*') if p.is_file()}
            # Independent synthetic later feed, no alteration to the archived original evidence.
            f=evidence('Unrelated company update')
            (root/'next-feed.xml').write_bytes(f['feed_raw']);(root/'next-receipt.json').write_bytes(f['feed_receipt_raw'])
            inputs['source_hashes'].pop('feed.xml');inputs['source_hashes'].pop('feed-receipt.json')
            for p in ('next-feed.xml','next-receipt.json'):inputs['source_hashes'][p]=sha256((root/p).read_bytes()).hexdigest()
            inputs.update(feed_path='next-feed.xml',feed_receipt_path='next-receipt.json')
            args.update(auto_review_inputs='next-inputs.json',auto_review_inputs_sha256=save('next-inputs.json',inputs))
            self.assertEqual(run(**args,execute=True)['status'],'MONTHLY_RUNTIME_PUBLISHED')
            self.assertEqual(len(calls),1);self.assertEqual(old,{p:p.read_bytes() for p in old_dir.rglob('*') if p.is_file()})

    def test_actual_outside_holding_requires_saved_close_and_account_revision(self):
        from test_current_quantity_v2_simulated_settlement import evidence_for
        from backtest.current_quantity_v2_simulated_settlement import settle,_references
        with TemporaryDirectory() as d:
            root,args,calls,daily,inputs,save=automatic_fixture(d)
            store=SimulationStore(daily['database_path']);saved=store.read(daily['simulation_id'])
            ev,through=evidence_for(saved['simulation']['chain'],_references(saved['simulation']['chain']))
            settled=store.apply(simulation_id=daily['simulation_id'],expected_revision=saved['revision'],operation_id='fixture-fill',request={'kind':'FIXTURE_FILL'},transform=lambda state:settle(simulation=state,evidence=ev,observed_through=through,evaluated_at=through))
            self.assertGreater(settled['simulation']['chain']['ledger']['shares'].get('A',0),0)
            inputs['expected_revision']=settled['revision'];args['auto_review_inputs_sha256']=save('automatic-inputs.json',inputs)
            before=Path(daily['database_path']).read_bytes()
            result=run(**args,execute=True)
            self.assertEqual(result['status'],'WAITING_REVIEW');self.assertEqual(result['reason'],'AUTO_REVIEW_HELD_CLOSE_DOMAIN_MISMATCH')
            self.assertEqual(Path(daily['database_path']).read_bytes(),before);self.assertFalse((root/'request.json').exists())

    def test_actual_outside_held_saved_daily_and_late_review_publish(self):
        from datetime import datetime
        from test_current_quantity_v2_simulated_settlement import evidence_for
        from backtest.current_quantity_v2_simulated_settlement import settle,_references
        from data.current_quantity_v2_simulation_origin_files import SimulationOriginFilesReader
        from data.current_quantity_v2_late_unit_review import BoundedLateUnitReview
        from data.current_quantity_v2_paper_action_sources import PaperActionEvidenceSources
        from data.current_quantity_v2_current_cash_sources import MANIFEST
        with TemporaryDirectory() as d:
            root,args,calls,daily,inputs,save=automatic_fixture(d)
            store=SimulationStore(daily['database_path']);saved=store.read(daily['simulation_id'])
            ev,through=evidence_for(saved['simulation']['chain'],_references(saved['simulation']['chain']))
            settled=store.apply(simulation_id=daily['simulation_id'],expected_revision=saved['revision'],operation_id='fixture-fill',request={'kind':'FIXTURE_FILL'},transform=lambda state:settle(simulation=state,evidence=ev,observed_through=through,evaluated_at=through))
            inputs['expected_revision']=settled['revision'];ref=_references(settled['simulation']['chain'])['A']
            old=json.loads((root/MANIFEST).read_bytes());oldrow=next(r for r in old['candidates'] if r['security_id']=='A')
            im=json.loads((root/'auto-identities.json').read_bytes());im['candidates'].append(oldrow);inputs['source_hashes']['auto-identities.json']=save('auto-identities.json',im)
            for path in oldrow['identity_source_references']:
                inputs['source_hashes'][path]=sha256((root/path).read_bytes()).hexdigest()
                doc=json.loads((root/path).read_bytes())
                for p,h in doc.get('source_hashes',{}).items():inputs['source_hashes'][p.replace('\\','/')]=h
            raw=(root/'new-held.json').read_bytes();captured='2026-11-03T10:00:00+00:00'
            inputs['source_hashes']['new-held.json']=sha256(raw).hexdigest()
            inputs['source_hashes']['held-receipt.json']=save('held-receipt.json',dict(security_id='A',ticker=ref['ticker'],target_date='2026-11-02',http_status=200,body_truncated=False,raw_sha256=sha256(raw).hexdigest(),started_at_utc=captured,received_at_utc=captured))
            now=datetime.fromisoformat('2026-11-03T11:00:00+00:00')
            def action(ticker,start,end):return dict(status=200,body=json.dumps(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY'),events={})]))).encode())
            public=PaperActionEvidenceSources(fetch=action,rss_fetch=lambda:dict(status=200,body=evidence()['feed_raw']),clock=lambda:now)
            package=BoundedLateUnitReview(action_sources=public,clock=lambda:now).capture(reference=ref,capture_raw=raw,captured_at=captured,origin_files=SimulationOriginFilesReader()(settled['simulation'],ref),account_id=settled['simulation']['chain']['ledger']['account_id'],state_revision=settled['revision'])
            for path,body in package['files'].items():
                target=root/path;target.parent.mkdir(parents=True,exist_ok=True)
                if target.exists():self.assertEqual(target.read_bytes(),body)
                else:target.write_bytes(body)
                inputs['source_hashes'][path]=sha256(body).hexdigest()
            inputs['held_bar_sources']={'A':dict(raw_path='new-held.json',receipt_path='held-receipt.json',unit_review_path=package['review_path'])}
            args['auto_review_inputs_sha256']=save('automatic-inputs.json',inputs);before=Path(daily['database_path']).read_bytes()
            result=run(**args,execute=True);self.assertEqual(result['status'],'MONTHLY_RUNTIME_PUBLISHED',result)
            self.assertEqual(Path(daily['database_path']).read_bytes(),before)
            self.assertEqual(json.loads((root/'request.json').read_bytes())['held_bar_sources'],{'A':'new-held.json'})

    def test_missing_account_and_revision_pause_before_capture(self):
        for mode in ('missing','revision'):
            with self.subTest(mode=mode),TemporaryDirectory() as d:
                root,args,calls,daily,inputs,save=automatic_fixture(d)
                if mode=='missing':Path(daily['database_path']).unlink()
                else:inputs['expected_revision']='0'*64;args['auto_review_inputs_sha256']=save('automatic-inputs.json',inputs)
                result=run(**args,execute=True);self.assertEqual(result['status'],'WAITING_REVIEW');self.assertEqual(calls,[]);self.assertFalse((root/'stages').exists())

if __name__=='__main__':unittest.main()
