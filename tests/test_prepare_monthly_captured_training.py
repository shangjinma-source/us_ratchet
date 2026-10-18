import unittest,json
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime
from hashlib import sha256
from copy import deepcopy
from data.current_quantity_v2_current_cash_plan import canonical
from test_current_quantity_v2_monthly_training import fixture as source_fixture
from scripts.prepare_monthly_captured_training import build

def fixture(folder):
    root=Path(folder);_,_,package,days=source_fixture(folder);files=deepcopy(package['files'])
    old=json.loads(files['manifest.json']);old['limitations']=[]
    def put(path,value):
        raw=value if isinstance(value,bytes) else canonical(value);files[path]=raw;return sha256(raw).hexdigest()
    op='previous.json';oldhash=put(op,old);session='2026-11-02'
    member={'schema':'ndx_current_quote_list_observation_v1','observed_symbols':['BBB','CCC'],'observed_security_count':2,'point_in_time_membership_verified':False}
    mh=put('members.json',member);ch=put('extension.json',dict(schema='SCHEDULED_REGULAR_SESSIONS_V1',source_hashes={'calendar-source':package['source_hashes']['calendar-source']},calendar=[session],sessions=[dict(date=session,timezone='America/New_York',open_at=session+'T09:30:00-05:00',close_at=session+'T16:00:00-05:00')]))
    plan=dict(schema='MONTHLY_FULL_DOMAIN_CAPTURE_PLAN_V1',membership_path='members.json',membership_source_hashes={'members.json':mh},calendar_path='extension.json',calendar_source_hashes={'extension.json':ch,'calendar-source':package['source_hashes']['calendar-source']},session=session,history_start_date=days[0],securities=[dict(ticker=r['ticker'],security_id=r['security_id'],security_type='EQUITY') for r in old['candidates']],output_directory='never-created')
    ph=put('plan.json',plan);entries=[]
    for r in old['candidates']:
        ticker=r['ticker'];obj=json.loads(files[r['training_source']]);c=obj['chart']['result'][0];c['timestamp'].append(int(datetime.fromisoformat(session+'T21:00:00+00:00').timestamp()))
        for key,values in c['indicators']['quote'][0].items():values.append(values[-1]+1)
        if r['price_coordinate_factors']:
            e=r['price_coordinate_factors'][0];c['events']={'splits':{'s':dict(date=int(datetime.fromisoformat(e['date']+'T15:00:00+00:00').timestamp()),numerator=3,denominator=1)}}
        rp='new/'+ticker+'.response.bin';rh=put(rp,obj);receipt=dict(status='RAW_CAPTURED',request_url='https://example.test/synthetic',final_url='https://example.test/synthetic',raw_sha256=rh,ticker=ticker,target_date=session,http_status=200,body_truncated=False,security_id=r['security_id'],security_type='EQUITY',started_at_utc='2026-11-03T10:00:00+00:00',received_at_utc='2026-11-03T10:00:01+00:00')
        hh=put('new/'+ticker+'.receipt.json',receipt);dh=put('new/'+ticker+'.decoded.json',dict(ticker=ticker,receipt_sha256=hh,decoded_sha256=rh,raw_returned_events=c.get('events',{})));entries.append(dict(ticker=ticker,security_id=r['security_id'],relative_directory='new',raw_sha256=rh,receipt_sha256=hh,decoded_sha256=dh,status='TRANSPORT_SAVED_UNRESOLVED_NOT_ADMITTED' if r['security_id'] is None else 'SAVED_EXACT_SESSION_READER_VALIDATED_NOT_ADMITTED'))
    bh=put('batch.json',dict(session=session,entries=[{k:v for k,v in e.items() if k!='relative_directory'} for e in entries if e['security_id'] is not None]));put('new/completion_index.json',{k:v for k,v in entries[-1].items() if k!='relative_directory'})
    ih=put('index.json',dict(plan_sha256=ph,session=session,entries=entries,batches=[dict(path='batch.json',sha256=bh)]))
    for p,raw in files.items():
        target=root/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    return dict(root=root,previous_manifest_path=op,previous_manifest_sha256=oldhash,capture_index_path='index.json',capture_index_sha256=ih,plan_path='plan.json',plan_sha256=ph,clock=lambda:datetime.fromisoformat('2026-11-03T11:00:00+00:00'))

class PreparationTests(unittest.TestCase):
    def test_raw_date_shift_retains_null_identity_and_compiles(self):
        with TemporaryDirectory() as folder:
            args=fixture(folder);m,c,r=build(**args)
            self.assertEqual(m['decision_date'],'2026-11-02');self.assertEqual(m['membership_observation_asof'],'2026-10-30')
            self.assertEqual(r['sessions'],253);self.assertEqual(set(c['input']['search_arguments']['prices']),{'B'})
            self.assertIsNone(m['candidates'][1]['security_id']);self.assertEqual(r['coverage'][1]['observed_sessions'],21)
            self.assertEqual(c['input']['search_arguments']['scenario_dates'],m['training_dates'][21::21])
    def test_future_session_and_receipt_rejected(self):
        with TemporaryDirectory() as folder:
            args=fixture(folder)
            for at in ('2026-11-02T20:59:00+00:00','2026-11-03T09:59:00+00:00'):
                args['clock']=lambda at=at:datetime.fromisoformat(at)
                with self.assertRaises(ValueError):build(**args)

    def test_rehashed_history_drift_new_split_and_tamper_reject(self):
        for mode in ('drift','split','hash','redirect','failed'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                args=fixture(folder);root=Path(folder);p=root/'new/BBB.response.bin';obj=json.loads(p.read_bytes())
                if mode in ('redirect','failed'):pass
                elif mode=='split':obj['chart']['result'][0]['events']['splits']['s']['numerator']=4
                else:obj['chart']['result'][0]['indicators']['quote'][0]['close'][20]+=1
                p.write_bytes(canonical(obj))
                if mode!='hash':
                    h=sha256(p.read_bytes()).hexdigest();rp=root/'new/BBB.receipt.json';rec=json.loads(rp.read_bytes());rec['raw_sha256']=h;
                    if mode=='redirect':rec['final_url']='https://other.test/'
                    if mode=='failed':rec['status']='FAILED'
                    rp.write_bytes(canonical(rec));idx=json.loads((root/'index.json').read_bytes());idx['entries'][0].update(raw_sha256=h,receipt_sha256=sha256(rp.read_bytes()).hexdigest());dp=root/'new/BBB.decoded.json';obs=json.loads(dp.read_bytes());obs.update(receipt_sha256=sha256(rp.read_bytes()).hexdigest(),decoded_sha256=h,raw_returned_events=obj['chart']['result'][0].get('events',{}));dp.write_bytes(canonical(obs));idx['entries'][0]['decoded_sha256']=sha256(dp.read_bytes()).hexdigest();batch=json.loads((root/'batch.json').read_bytes());batch['entries'][0]={k:v for k,v in idx['entries'][0].items() if k!='relative_directory'};(root/'batch.json').write_bytes(canonical(batch));idx['batches'][0]['sha256']=sha256((root/'batch.json').read_bytes()).hexdigest();(root/'index.json').write_bytes(canonical(idx));args['capture_index_sha256']=sha256((root/'index.json').read_bytes()).hexdigest()
                with self.assertRaises(ValueError):build(**args)

if __name__=='__main__':unittest.main()
