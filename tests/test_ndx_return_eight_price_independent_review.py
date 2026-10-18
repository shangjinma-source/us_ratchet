import copy
import gzip
import hashlib
import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from decimal import localcontext, Inexact, Rounded, ROUND_UP
from scripts import ndx_return_eight_price_only_20260923 as m


def fixture(ticker):
    sealed=m.PATHS[ticker].read_bytes()
    assert hashlib.sha256(sealed).hexdigest()==m.HASHES[ticker]
    doc=json.loads(sealed);result=doc['result']
    calendar=[d for d in json.loads(m.CALENDAR.read_bytes())['calendar'] if '2023-03-31'<=d<='2023-09-01']
    return dict(ticker=ticker,raw=m.Path(doc['raw_path']).read_bytes(),raw_sha256=doc['raw_sha256'],
                request=result['original_request'],received_at_utc=result['original_received_at_utc'],
                calendar=calendar,rows=result['reconstruction']['rows'],basis=result['conditional_quote_basis'])


def change_raw(args,callback):
    raw=args['raw'];document=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)
    callback(document['chart']['result'][0])
    args['raw']=json.dumps(document).encode();args['raw_sha256']=hashlib.sha256(args['raw']).hexdigest()


class IndependentReview(unittest.TestCase):
    def test_all_eight_exact_107_and_1712_cells(self):
        cells=0
        for ticker in m.HASHES:
            result=m.inspect_channel(**fixture(ticker));cells+=result['cells_checked']
            self.assertEqual(len(result['rows']),107)
            self.assertEqual({row['factor_numerator'] for row in result['rows']},{'10' if ticker=='AVGO' else '1'})
            self.assertEqual(result['window_event_counts']['splits'],0)
        self.assertEqual(cells,1712)

    def test_avgo_double_application_rejected(self):
        args=fixture('AVGO');row=next(r for r in args['rows'] if r['session']==args['calendar'][0])
        row['nominal_open']*=10
        with self.assertRaises(ValueError):m.inspect_channel(**args)

    def test_front_window_splits_not_reapplied_or_silently_dropped(self):
        for ticker,factor in [('FTNT',5),('GOOG',20),('GOOGL',20)]:
            args=fixture(ticker);row=next(r for r in args['rows'] if r['session']==args['calendar'][0]);row['nominal_close']*=factor
            with self.assertRaises(ValueError):m.inspect_channel(**args)
            args=fixture(ticker);change_raw(args,lambda d:d['events'].pop('splits'))
            with self.assertRaises(ValueError):m.inspect_channel(**args)

    def test_dividend_does_not_change_prices(self):
        args=fixture('AMAT');baseline=m.inspect_channel(**args)['rows']
        def dividend(data):
            stamp=next(t for t in data['timestamp'] if m.day(t)==args['calendar'][0])
            data.setdefault('events',{}).setdefault('dividends',{})[str(stamp)]={'date':stamp,'amount':999}
        change_raw(args,dividend)
        self.assertEqual(m.inspect_channel(**args)['rows'],baseline)

    def test_bool_duplicate_missing_and_raw_hash_rejected(self):
        base=fixture('BKR');index=next(i for i,r in enumerate(base['rows']) if r['session']==base['calendar'][0])
        for edit in [lambda a:a['rows'][index].update(nominal_open=True),
                     lambda a:a['rows'].pop(index),lambda a:a['rows'].insert(index,copy.deepcopy(a['rows'][index])),
                     lambda a:a.update(raw_sha256='0'*64),lambda a:a['calendar'].pop(1)]:
            args=copy.deepcopy(base);edit(args)
            with self.assertRaises(ValueError):m.inspect_channel(**args)
        for raw in (b'{"chart":{},"chart":{}}',b'{"x":NaN}'):
            with self.assertRaises(ValueError):m.loads(raw)
        args=fixture('BKR')
        def invalid(data):
            index=next(i for i,t in enumerate(data['timestamp']) if m.day(t)==args['calendar'][0])
            data['indicators']['quote'][0]['open'][index]=True
        change_raw(args,invalid)
        with self.assertRaises(ValueError):m.inspect_channel(**args)

    def test_caller_decimal_context_does_not_affect_results(self):
        args=fixture('AVGO');expected=m.inspect_channel(**args)
        with localcontext() as context:
            context.prec=2;context.rounding=ROUND_UP;context.traps[Inexact]=True;context.traps[Rounded]=True
            self.assertEqual(m.inspect_channel(**args),expected)

    def test_source_drift_and_existing_namespace_block_publication(self):
        for after in (False,True):
            with tempfile.TemporaryDirectory() as folder:
                source=Path(folder)/'source';source.write_bytes(b'old')
                sources={str(source):hashlib.sha256(b'old').hexdigest()}
                if not after:source.write_bytes(b'new')
                with patch.object(m.os,'fsync',side_effect=lambda _:source.write_bytes(b'new')):
                    with self.assertRaisesRegex(ValueError,'Source drift'):
                        m.publish(Path(folder)/'artifact',{'value':1},sources)
                with patch.object(m,'build') as build:
                    with self.assertRaisesRegex(ValueError,'already exists'):m.run(folder)
                    build.assert_not_called()

    def test_verify_rejects_matrix_denominator_or_flag_tampering(self):
        expected={'matrices':{'open':{'2023-03-31':{'AVGO':'100'}}},'price_cell_count':1712,
                  'point_in_time_verified':False}
        with patch.object(m,'build',return_value=expected):
            m.verify(expected)
            for field,value in [('price_cell_count',1711),('point_in_time_verified',True),('matrices',{})]:
                changed=copy.deepcopy(expected);changed[field]=value
                with self.assertRaises(ValueError):m.verify(changed)


if __name__=='__main__':unittest.main()
