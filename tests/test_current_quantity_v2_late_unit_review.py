from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest

from data.current_quantity_v2_late_unit_review import BoundedLateUnitReview, replay, STATUS
from data.current_quantity_v2_paper_action_sources import PaperActionEvidenceSources

NOW = datetime.fromisoformat('2026-10-16T14:00:00+00:00')
ORIGIN = b'synthetic original source bytes'


def provider(*, events=None, title='Unrelated notice', publication='Fri, 16 Oct 2026 13:00:00 GMT', name=None):
    def daily(ticker, start, end):
        return dict(status=200, body=json.dumps(dict(chart=dict(error=None, result=[dict(
            meta=dict(symbol=ticker, currency='USD', instrumentType='EQUITY',longName=name), events=events or {})]))).encode())
    rss = ('<rss><channel><title>Nasdaq</title><item><title>'+title+'</title>'
           '<pubDate>'+publication+'</pubDate></item></channel></rss>').encode()
    source = PaperActionEvidenceSources(fetch=daily, rss_fetch=lambda:dict(status=200,body=rss), clock=lambda:NOW)
    return BoundedLateUnitReview(action_sources=source, clock=lambda:NOW)


def origins(reference):
    raw=json.dumps(dict(chart=dict(result=[dict(meta=dict(symbol=reference['ticker'],currency='USD',instrumentType='EQUITY'))]))).encode()
    path='origin/'+reference['security_id']+'.raw'
    receipt=json.dumps(dict(security_id=reference['security_id'],ticker=reference['ticker'],captured_at=reference['captured_at'],raw_path=path,raw_sha256=sha256(raw).hexdigest())).encode()
    return {path:raw,path+'.json':receipt}


def generate(reference, raw, captured):
    return provider().capture(reference=reference, capture_raw=raw, captured_at=captured,
        origin_files=origins(reference), account_id='isolated', state_revision='r1')


def publish(root, package):
    for path,raw in package['files'].items():
        target=root/path; target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists(): assert target.read_bytes()==raw
        else: target.write_bytes(raw)


def real_pin_fixture():
    from test_current_quantity_v2_difference_plan import fixture
    args=fixture();args['source_hashes']['source']=sha256(ORIGIN).hexdigest()
    for ref in args['execution_references'].values():
        pins={p:sha256(raw).hexdigest() for p,raw in origins(ref).items()}
        args['source_hashes'].update(pins);ref['source_hashes']=pins
        args['unit_continuity'][ref['security_id']]['reference_source_hashes']=pins
    return args


class LateReviewTests(unittest.TestCase):
    def test_unresolved_publication_and_html_encoded_name_are_rejected(self):
        ref=dict(security_id='A',ticker='AAA',price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',
                 captured_at='2026-10-15T16:00:30+00:00')
        ref['source_hashes']={p:sha256(raw).hexdigest() for p,raw in origins(ref).items()}
        raw=json.dumps(dict(chart=dict(result=[dict(meta=dict(symbol='AAA',currency='USD',instrumentType='EQUITY'))]))).encode()
        cases=[(provider(publication=''),'LATE_UNIT_REVIEW_UNAVAILABLE'),
               (provider(publication='Sat, 17 Oct 2026 13:00:00 GMT'),'LATE_UNIT_REVIEW_UNAVAILABLE'),
               (provider(name='Alpha Business Corporation',title='Alpha&amp;nbsp;&lt;b&gt;Business&lt;/b&gt; Corporation split'),'LATE_UNIT_CHANGE_CANDIDATE')]
        for source,reason in cases:
            with self.assertRaisesRegex(ValueError,reason):
                source.capture(reference=ref,capture_raw=raw,captured_at=NOW,origin_files=origins(ref),account_id='isolated',state_revision='r1')

    def test_current_cash_genesis_reference_uses_actual_frozen_quote_bytes(self):
        import test_current_quantity_v2_current_cash_plan as base
        from test_current_quantity_v2_current_cash_ledger import frozen_fixture
        from data.current_quantity_v2_paper_ledger import accept_proposal
        from data.current_quantity_v2_paper_chain import create_chain
        from backtest.current_quantity_v2_simulated_settlement import _references
        base.CurrentCashTests.setUpClass()
        try:
            proposal,args=frozen_fixture(base.CurrentCashTests.args)
            chain=create_chain(accept_proposal(proposal,account_state=args['account_state'],now=args['now']))
            for sid,ref in _references(chain).items():
                self.assertEqual(ref['security_id'],sid)
                raw=json.dumps(dict(chart=dict(result=[dict(meta=dict(symbol=ref['ticker'],currency='USD',instrumentType='EQUITY'))]))).encode()
                package=provider().capture(reference=ref,capture_raw=raw,captured_at=NOW,
                    origin_files=args['execution_package']['files'],account_id=proposal['account_id'],state_revision='r1')
                review=json.loads(package['files'][package['review_path']])
                self.assertEqual(replay(review,reference=ref,capture_raw_sha256=sha256(raw).hexdigest(),
                    captured_at=NOW,observed_at=NOW,read=package['files'].__getitem__)['status'],STATUS)
        finally:base.CurrentCashTests.tearDownClass()

    def test_frozen_late_replay_and_binding_failures(self):
        ref=dict(security_id='A',ticker='AAA',price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',
                 captured_at='2026-10-15T16:00:30+00:00',source_hashes={'source':sha256(ORIGIN).hexdigest()})
        ref['source_hashes']={p:sha256(raw).hexdigest() for p,raw in origins(ref).items()}
        raw=json.dumps(dict(chart=dict(result=[dict(meta=dict(symbol='AAA',currency='USD',instrumentType='EQUITY'))]))).encode()
        p=generate(ref,raw,NOW);review=json.loads(p['files'][p['review_path']])
        kwargs=dict(reference=ref,capture_raw_sha256=sha256(raw).hexdigest(),captured_at=NOW,
                    observed_at=NOW,read=p['files'].__getitem__)
        result=replay(review,**kwargs)
        self.assertEqual(result['status'],STATUS);self.assertFalse(result['coverage_complete'])
        for key,value in [('capture_raw_sha256','0'*64),('reference_sha256','0'*64),
                          ('covered_through','2026-10-15T20:00:00+00:00'),('status','NO_UNPROCESSED_ACTIONS')]:
            with self.subTest(key=key):
                changed=deepcopy(review);changed[key]=value
                with self.assertRaises(ValueError):replay(changed,**kwargs)
        p['files'][review['bounded_evidence']['rss_raw_path']]=b'changed'
        with self.assertRaises(ValueError):replay(review,**kwargs)
        for source in (provider(events={'splits':{'x':{'date':1}}}),provider(title='AAA reverse split')):
            with self.assertRaisesRegex(ValueError,'LATE_UNIT_CHANGE_CANDIDATE'):
                source.capture(reference=ref,capture_raw=raw,captured_at=NOW,origin_files=origins(ref),
                               account_id='isolated',state_revision='r1')

    def test_actual_daily_consumer_replays_bounded_proof(self):
        from test_current_quantity_v2_daily_settlement_simulation import setup
        from backtest.current_quantity_v2_daily_settlement_simulation import prepare_daily_settlement,apply_daily_settlement
        from backtest.current_quantity_v2_simulated_settlement import _references
        from data.current_quantity_v2_paper_ledger import digest
        with TemporaryDirectory() as folder,patch('test_current_quantity_v2_paper_ledger.fixture',side_effect=real_pin_fixture):
            store,current,args,_=setup(folder);prepared=prepare_daily_settlement(**args);root=Path(prepared['directory'])
            paths={};pins={}
            for sid,ref in _references(current['simulation']['chain']).items():
                capture=root/digest(sid);receipt=json.loads((capture/'receipt.json').read_bytes())
                p=generate(ref,(capture/'response.bin').read_bytes(),receipt['captured_at']);publish(root,p)
                paths[sid]=p['review_path'];pins.update(p['source_hashes'])
            result=apply_daily_settlement(store=store,prepared=prepared,unit_reviews=paths,source_hashes=pins,evaluated_at=NOW.isoformat())
            self.assertTrue(all(o['closed']=='FILLED' for o in result['simulation']['chain']['ledger']['orders'].values()))

    def test_actual_close_consumer_requires_replay_not_status_only(self):
        from test_current_quantity_v2_minute_close_marks import fixture
        from data.current_quantity_v2_minute_close_marks import build_marks
        from backtest.current_quantity_v2_simulated_settlement import _references
        with TemporaryDirectory() as folder,patch('test_current_quantity_v2_paper_ledger.fixture',side_effect=real_pin_fixture):
            _,args=fixture(folder);root=Path(folder)
            for sid,ref in _references(args['chain']).items():
                if sid not in args['captures']:continue
                paths=args['captures'][sid];receipt=json.loads((root/paths['receipt']).read_bytes())
                p=generate(ref,(root/paths['raw']).read_bytes(),receipt['captured_at']);publish(root,p)
                args['unit_reviews'][sid]=p['review_path'];args['source_hashes'].update(p['source_hashes'])
            result=build_marks(**args)
            self.assertTrue(all(m['unit_review_scope']=='BOUNDED_PUBLIC_SCREENING_MAY_MISS_ACTIONS' for m in result['marks'].values()))
            name=next(iter(args['unit_reviews'].values()));review=json.loads((root/name).read_bytes())
            review.pop('bounded_evidence');raw=json.dumps(review).encode();(root/name).write_bytes(raw)
            args['source_hashes'][name]=sha256(raw).hexdigest()
            with self.assertRaises(ValueError):build_marks(**args)


if __name__=='__main__':unittest.main()
