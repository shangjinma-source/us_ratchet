from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from data.current_quantity_v2_completed_session_minutes import capture
from data.current_quantity_v2_minute_close_marks import build_marks
from data.current_quantity_v2_paper_ledger import digest
from backtest.current_quantity_v2_simulated_settlement import settle, record_close
from test_current_quantity_v2_simulated_settlement import valuation_fixture


def fixture(folder):
    root=Path(folder);state,evidence,args,calendar=valuation_fixture()
    state=settle(simulation=state,evidence=evidence,observed_through='2026-10-15T12:02:00-04:00',
                 evaluated_at='2026-10-15T12:02:00-04:00')
    now=datetime.fromisoformat('2026-10-16T10:00:00-04:00');captures={};reviews={};pins={}
    def save(path,value):
        raw=value if isinstance(value,bytes) else json.dumps(value,sort_keys=True).encode()
        (root/path).write_bytes(raw);pins[path]=sha256(raw).hexdigest()
    for sid,q in state['chain']['ledger']['shares'].items():
        if not q:continue
        ref=args['execution_references'][sid];opening=datetime.fromisoformat(ref['session_open'])
        closing=datetime.fromisoformat(ref['session_close']);count=int((closing-opening).total_seconds()/60)
        body=json.dumps(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ref['ticker'],currency='USD',
            instrumentType='EQUITY',dataGranularity='1m',exchangeTimezoneName='America/New_York'),
            timestamp=[int(opening.timestamp())+i*60 for i in range(count)],
            indicators={'quote':[{**{k:[2]*count for k in ('open','high','low','close')},'volume':[1]*count}]})]))).encode()
        capture(directory=root/sid,security_id=sid,ticker=ref['ticker'],session='2026-10-15',
                session_open=ref['session_open'],session_close=ref['session_close'],
                calendar_source_reference='synthetic-calendar',fetch=lambda _,body=body:body,clock=lambda:now)
        captures[sid]=dict(raw=sid+'/response.bin',receipt=sid+'/receipt.json',minutes=sid+'/minutes.json')
        for path in captures[sid].values():pins[path]=sha256((root/path).read_bytes()).hexdigest()
        source=sid+'/unit-evidence.json';save(source,{'scope':'EXPLICIT_SYNTHETIC_UNIT_DECLARATION'})
        review=sid+'/unit-review.json'
        save(review,dict(security_id=sid,ticker=ref['ticker'],price_basis=ref['price_basis'],
            status='NO_UNPROCESSED_ACTIONS',reference_sha256=digest(ref),reference_source_hashes=ref['source_hashes'],
            capture_raw_sha256=sha256(body).hexdigest(),covered_from=ref['captured_at'],covered_through=now.isoformat(),
            reviewed_at=now.isoformat(),source_references=[source]))
        reviews[sid]=review
    return state,dict(root=root,chain=state['chain'],session='2026-10-15',
        session_close=calendar['closes']['2026-10-15'],captures=captures,source_hashes=pins,
        unit_reviews=reviews,observed_at=now.isoformat())


class MinuteCloseMarksTests(unittest.TestCase):
    def test_real_saved_capture_to_record_close_no_initial_backfill(self):
        with TemporaryDirectory() as folder:
            state,args=fixture(folder);before=deepcopy(state);result=build_marks(**args)
            self.assertFalse(result['official_close']);self.assertFalse(result['initial_valuation_supported'])
            self.assertEqual(set(result['marks']),{s for s,q in state['chain']['ledger']['shares'].items() if q})
            for mark in result['marks'].values():
                self.assertEqual(mark['mark_method'],'LAST_COMPLETE_MINUTE_CLOSE_PROXY')
                self.assertEqual(mark['observed_at'],'2026-10-16T14:00:00+00:00')
            updated=record_close(simulation=state,session=args['session'],marks=result['marks'],observed_at=args['observed_at'])
            self.assertEqual(updated['valuation']['records'][0]['status'],'COMPLETE')
            self.assertEqual(state,before)

    def test_missing_held_last_minute_identity_unit_or_hash_refused(self):
        for mode in ('held','last','identity','session','unit','hash','missing_review','close_only','wrong_raw','wrong_reference','string_refs'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                _,args=fixture(folder);sid=next(iter(args['captures']));root=Path(folder)
                if mode=='held':args['captures'].pop(sid)
                elif mode=='missing_review':args['unit_reviews'].pop(sid)
                elif mode=='hash':(root/args['captures'][sid]['raw']).write_bytes(b'changed')
                else:
                    key='raw' if mode=='last' else 'receipt'
                    path=args['unit_reviews'][sid] if mode in ('unit','close_only','wrong_raw','wrong_reference','string_refs') else args['captures'][sid][key]
                    value=json.loads((root/path).read_bytes())
                    if mode=='last':
                        chart=value['chart']['result'][0];chart['timestamp'].pop()
                        for values in chart['indicators']['quote'][0].values():values.pop()
                    elif mode=='identity':value['ticker']='WRONG'
                    elif mode=='session':value['session']='2026-10-14'
                    elif mode=='close_only':value['covered_through']=args['session_close']
                    elif mode=='wrong_raw':value['capture_raw_sha256']='0'*64
                    elif mode=='wrong_reference':value['reference_sha256']='0'*64
                    elif mode=='string_refs':value['source_references']='x'
                    else:value['price_basis']='DIFFERENT_SHARE_UNITS'
                    raw=json.dumps(value).encode();(root/path).write_bytes(raw);args['source_hashes'][path]=sha256(raw).hexdigest()
                    if mode=='last':
                        path=args['captures'][sid]['receipt'];receipt=json.loads((root/path).read_bytes())
                        receipt['raw_sha256']=sha256(raw).hexdigest();raw=json.dumps(receipt).encode()
                        (root/path).write_bytes(raw);args['source_hashes'][path]=sha256(raw).hexdigest()
                with self.assertRaises(ValueError):build_marks(**args)


if __name__=='__main__':unittest.main()
