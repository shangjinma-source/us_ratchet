from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from core.strategy_account_ledger import canonical
from data.strategy_prospective_paper_daily_capture_v1 import capture_prospective_daily,load_prospective_daily_archive,CODE_PATHS
from data.strategy_verified_context_daily_normalizer_v1 import NORMALIZATION_CODE_PATHS
from data.strategy_prospective_paper_selection_v1 import select_prospective_target
from backtest.current_strategy_prospective_paper_book_v1 import create_book
from test_strategy_prospective_paper_integration_v1 import fixture

ROOT=Path(__file__).resolve().parents[1]


def arguments(folder):
    root=Path(folder);(root/'initial').mkdir()
    daily=fixture(root/'initial',extra_code_paths=CODE_PATHS)
    parent_raw=daily['receipt_bytes'];parent_path='approved-parent.json'
    authority=deepcopy(daily['authority']);context=authority['descriptor_arguments']
    context['source_bytes'][parent_path]=parent_raw
    security=dict(security_id='B',ticker='B',currency='USD',exchangeName='NMS',instrumentType='EQUITY')
    context['source_bytes']['identity.json']=canonical(dict(schema='SERVER_CAPTURE_IDENTITY_V1',review_status='REVIEWED',security=security))
    descriptor=json.loads(context['descriptor_bytes']);descriptor['source_sha256']={p:sha256(raw).hexdigest() for p,raw in context['source_bytes'].items()}
    context['descriptor_bytes']=canonical(descriptor);context['trusted_descriptor_sha256']=sha256(context['descriptor_bytes']).hexdigest()
    approval=json.loads(context['approval_bytes']);approval['descriptor_sha256']=context['trusted_descriptor_sha256']
    context['approval_bytes']=canonical(approval);context['trusted_approval_sha256']=sha256(context['approval_bytes']).hexdigest()
    registration=json.loads(authority['registration_bytes']);registration['descriptor_sha256']=context['trusted_descriptor_sha256']
    authority['registration_bytes']=canonical(registration);authority['trusted_registration_sha256']=sha256(authority['registration_bytes']).hexdigest()
    book=create_book(authority=authority,clock=lambda:datetime.fromisoformat('2026-11-03T15:00:00+00:00'))
    selection=deepcopy(daily['selection_arguments']);selection.update(book=book,authority=authority)
    package=selection['source_package'];units=json.loads(package['files']['review.paper.json']);units['account_revision']=book['revision']
    package['files']['review.paper.json']=canonical(units);package['source_hashes']['review.paper.json']=sha256(package['files']['review.paper.json']).hexdigest()
    review=json.loads(selection['source_review_bytes']);review.update(descriptor_sha256=book['descriptor_sha256'],account_revision=book['revision'],source_sha256=package['source_hashes'])
    selection['source_review_bytes']=canonical(review);selection['trusted_source_review_sha256']=sha256(selection['source_review_bytes']).hexdigest()
    selected=select_prospective_target(clock=lambda:selection['now'],**selection)
    def write(path,raw):
        target=root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        return dict(path=path,sha256=sha256(raw).hexdigest())
    parent=write(parent_path,parent_raw)
    for path,raw in daily['files'].items():write(path,raw)
    calendar=write('calendar.json',context['calendar_bytes'])
    security=dict(security_id='B',ticker='B',currency='USD',exchangeName='NMS',instrumentType='EQUITY')
    identity=write('identity.json',canonical(dict(schema='SERVER_CAPTURE_IDENTITY_V1',review_status='REVIEWED',security=security)))
    pins=[write(path,(ROOT/path).read_bytes()) for path in NORMALIZATION_CODE_PATHS]
    config=canonical(dict(schema='SERVER_DAILY_SESSION_CAPTURE_V1',calendar=calendar,identity_review=identity,security=security,source_pins=pins,output_root='captured/B'))
    inputs=json.loads(daily['files']['normalized.json']);history=inputs['histories']['B']
    rows={r['date']:r for r in json.loads(context['calendar_bytes'])['sessions']}
    closes=[float(r['close']) for r in history['closes']]
    times=[int(datetime.fromisoformat(rows[r['date']]['open']).timestamp()) for r in history['closes']]
    raw=canonical(dict(chart=dict(error=None,result=[dict(meta={k:v for k,v in security.items() if k!='security_id'},timestamp=times,
        indicators=dict(quote=[dict(close=closes)],adjclose=[dict(adjclose=closes)]),events={})])))
    # Yahoo metadata uses symbol rather than ticker.
    parsed=json.loads(raw);parsed['chart']['result'][0]['meta']['symbol']='B';raw=canonical(parsed)
    rss=b'<rss><channel><title>Nasdaq</title><pubDate>Tue, 03 Nov 2026 14:00:00 GMT</pubDate><item><title>Unrelated notice</title><pubDate>Tue, 03 Nov 2026 14:00:00 GMT</pubDate></item></channel></rss>'
    calls=[]
    def fetch(*unused):calls.append('daily');return dict(status=200,body=raw)
    def official():calls.append('official');return dict(status=200,body=rss)
    return dict(root=root,book=book,authority=authority,admitted_decisions={},selection_result=selected,selection_arguments=selection,
        release_path='policy/daily.json',capture_requests={'B':dict(parent_reference=parent,configuration_bytes=config,configuration_sha256=sha256(config).hexdigest())},
        output_directory=root/'published',clock=lambda:datetime.fromisoformat('2026-11-03T15:00:10+00:00'),fetch_daily=fetch,fetch_official=official),calls


class DailyCaptureTests(unittest.TestCase):
    def test_actual_capture_normalize_formal_signal(self):
        with TemporaryDirectory() as folder:
            args,calls=arguments(folder);before=deepcopy(args['book'])
            result=capture_prospective_daily(**args)
            self.assertEqual(result['status'],'DAILY_SIGNAL_READY')
            self.assertEqual(result['verified']['signal']['effective_target_quantities'],{'B':10})
            self.assertEqual(calls,['daily','official']);self.assertEqual(args['book'],before)
            self.assertTrue((Path(folder)/'published'/'receipt.json').is_file())
            loaded=load_prospective_daily_archive(directory=result['directory'],trusted_complete_sha256=result['archive_complete_sha256'],
                daily_arguments=result['daily_arguments'],clock=args['clock'])
            self.assertEqual(loaded['verified'],result['verified'])

    def test_unregistered_parent_rejected_before_http(self):
        with TemporaryDirectory() as folder:
            args,calls=arguments(folder)
            args['capture_requests']['B']['parent_reference']['sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'PARENT_NOT_REGISTERED'):capture_prospective_daily(**args)
            self.assertEqual(calls,[])

    def test_overlap_changed_and_repeated_capture_never_publish(self):
        with TemporaryDirectory() as folder:
            args,calls=arguments(folder);original=args['fetch_daily']
            def changed(*values):
                response=original(*values);payload=json.loads(response['body']);row=payload['chart']['result'][0]
                row['indicators']['quote'][0]['close'][0]+=1
                row['indicators']['adjclose'][0]['adjclose'][0]+=1
                return dict(response,body=canonical(payload))
            args['fetch_daily']=changed
            with self.assertRaisesRegex(ValueError,'PRICE_CONTINUITY_REVIEW'):capture_prospective_daily(**args)
            self.assertEqual(calls,['daily','official']);self.assertFalse((Path(folder)/'published').exists())
            with self.assertRaisesRegex(ValueError,'CAPTURE_INCOMPLETE'):capture_prospective_daily(**args)
            self.assertEqual(calls,['daily','official'])

    def test_unregistered_identity_rejected_before_http(self):
        with TemporaryDirectory() as folder:
            args,calls=arguments(folder);request=args['capture_requests']['B']
            config=json.loads(request['configuration_bytes']);config['identity_review']['sha256']='0'*64
            request['configuration_bytes']=canonical(config);request['configuration_sha256']=sha256(request['configuration_bytes']).hexdigest()
            with self.assertRaisesRegex(ValueError,'IDENTITY_NOT_REGISTERED'):capture_prospective_daily(**args)
            self.assertEqual(calls,[])

    def test_current_rss_rules_preserve_unrelated_future_but_reject_issuer_and_bad_time(self):
        for mode in ('unrelated_future','issuer_future','bad_time'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                args,calls=arguments(folder);fetch=args['fetch_daily']
                def named(*values):
                    response=fetch(*values);doc=json.loads(response['body'])
                    doc['chart']['result'][0]['meta']['longName']='Example Therapeutics'
                    return dict(response,body=canonical(doc))
                args['fetch_daily']=named
                title='Example Therapeutics stock split' if mode=='issuer_future' else 'Unrelated scheduled notice'
                date='broken date' if mode=='bad_time' else 'Wed, 04 Nov 2026 14:00:00 GMT'
                raw=('<rss><channel><title>Nasdaq</title><pubDate>Tue, 03 Nov 2026 14:00:00 GMT</pubDate>'
                    '<item><title>'+title+'</title><pubDate>'+date+'</pubDate></item></channel></rss>').encode()
                args['fetch_official']=lambda:dict(status=200,body=raw)
                if mode=='unrelated_future':
                    result=capture_prospective_daily(**args);self.assertEqual(result['status'],'DAILY_SIGNAL_READY')
                else:
                    with self.assertRaisesRegex(ValueError,'CAPTURE_INCOMPLETE'):capture_prospective_daily(**args)
                    self.assertFalse((Path(folder)/'published').exists())
                archived=Path(folder)/'captured'/'B'/'2026-11-03'/'official.response.bin'
                self.assertEqual(archived.read_bytes(),raw)

    def test_clock_expiring_after_archive_leaves_explicit_failure(self):
        with TemporaryDirectory() as folder:
            args,calls=arguments(folder);receipt=Path(folder)/'published'/'receipt.json'
            args['clock']=lambda:datetime.fromisoformat('2026-11-03T21:00:00+00:00' if receipt.exists() else '2026-11-03T15:00:10+00:00')
            with self.assertRaisesRegex(ValueError,'PAPER_DAILY_CAPTURE_CLOCK'):capture_prospective_daily(**args)
            self.assertTrue(receipt.exists())
            self.assertTrue(json.loads((receipt.parent/'failed.json').read_bytes())['receipt_is_not_admission'])

    def test_reopen_refuses_incomplete_archive_and_changed_blob(self):
        for mode in ('incomplete','blob','failed','expired'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                args,calls=arguments(folder);result=capture_prospective_daily(**args);directory=Path(result['directory'])
                clock=args['clock']
                if mode=='incomplete':(directory/'complete.json').unlink()
                elif mode=='failed':(directory/'failed.json').write_text('{}',encoding='utf8')
                elif mode=='expired':clock=lambda:datetime.fromisoformat('2026-11-03T21:00:00+00:00')
                else:
                    path=next((directory/'files').glob('*.bin'));path.write_bytes(path.read_bytes()+b' ')
                expected={'incomplete':'ARCHIVE_FILE','blob':'ARCHIVE_BLOB_HASH',
                          'failed':'ARCHIVE_FAILED','expired':'ARCHIVE_EXPIRED'}[mode]
                with self.assertRaisesRegex(ValueError,expected):
                    load_prospective_daily_archive(directory=directory,trusted_complete_sha256=result['archive_complete_sha256'],
                        daily_arguments=result['daily_arguments'],clock=clock)


if __name__=='__main__':unittest.main()
