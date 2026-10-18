import copy
import gzip
import hashlib
import json
import unittest
from scripts import ndx_seven_ticker_price_only_20260919 as m


def fixture(ticker):
    path=m.PATHS[ticker];rawdoc=path.read_bytes()
    assert hashlib.sha256(rawdoc).hexdigest()==m.HASHES[ticker]
    doc=json.loads(rawdoc);result=doc['result']
    calendar=[d for d in json.loads(m.CALENDAR.read_bytes())['calendar'] if '2023-03-31'<=d<='2023-05-01']
    if ticker=='ENPH':
        folder=m.BASE/'legacy_pool_remaining_split_probe_20260912_v1';meta=json.loads((folder/'ENPH.metadata.json').read_bytes())
        raw=(folder/'ENPH.response.bin').read_bytes();sha=meta['response_sha256'];request=meta['request'];receipt=meta['received_at_utc'];rows=result['rows'];basis=result['quote_field_basis']
    else:
        raw=m.Path(doc['raw_path']).read_bytes();sha=doc['raw_sha256'];request=result['original_request'];receipt=result['original_received_at_utc'];rows=result['reconstruction']['rows'];basis=result['conditional_quote_basis']
    return dict(ticker=ticker,raw=raw,raw_sha256=sha,request=request,received_at_utc=receipt,calendar=calendar,rows=rows,basis=basis)


def change_raw(args,callback):
    data=json.loads(gzip.decompress(args['raw']) if args['raw'][:2]==b'\x1f\x8b' else args['raw'])
    callback(data['chart']['result'][0])
    args['raw']=json.dumps(data).encode();args['raw_sha256']=hashlib.sha256(args['raw']).hexdigest()


class Tests(unittest.TestCase):
    def test_all_seven_actual_raw_bounded_decimal_no_build(self):
        for ticker in m.HASHES:
            with self.subTest(ticker=ticker):
                value=m.inspect_channel(**fixture(ticker))
                self.assertEqual(value['cells_checked'],42)
                self.assertEqual({r['factor_numerator'] for r in value['rows']},{'10' if ticker=='AVGO' else '1'})
                if ticker=='FTNT':self.assertTrue(value['all_returned_raw_events']['splits'])

    def test_forged_nominal_factor_bool_and_missing_date_reject(self):
        base=fixture('AVGO')
        index=next(i for i,r in enumerate(base['rows']) if r['session']==base['calendar'][0])
        changes=[lambda a:a['rows'][index].update(nominal_open=1),lambda a:a['rows'][index].update(split_factor=True),
            lambda a:a['rows'].pop(index),lambda a:a['rows'].insert(index,copy.deepcopy(a['rows'][index])),lambda a:a.update(basis='ADJCLOSE')]
        for change in changes:
            args=copy.deepcopy(base);change(args)
            with self.assertRaises(ValueError):m.inspect_channel(**args)

    def test_unmatched_or_window_event_and_dividend_is_separate(self):
        args=fixture('AVGO')
        def ratio(data):next(iter(data['events']['splits'].values()))['numerator']=11
        change_raw(args,ratio)
        with self.assertRaises(ValueError):m.inspect_channel(**args)
        args=fixture('AMAT');baseline=m.inspect_channel(**args)
        def dividend(data):
            stamp=next(t for t in data['timestamp'] if m.day(t)==args['calendar'][0])
            data.setdefault('events',{}).setdefault('dividends',{})[str(stamp)]={'date':stamp,'amount':999}
        change_raw(args,dividend)
        self.assertEqual(m.inspect_channel(**args)['rows'],baseline['rows'])
        def split(data):
            stamp=next(t for t in data['timestamp'] if m.day(t)==args['calendar'][0])
            data['events']['splits']={str(stamp):dict(date=stamp,numerator=2,denominator=1,splitRatio='2:1')}
        change_raw(args,split)
        with self.assertRaises(ValueError):m.inspect_channel(**args)

    def test_raw_hash_horizon_and_channel_coordinates_reject(self):
        args=fixture('FTNT');args['raw_sha256']='0'*64
        with self.assertRaises(ValueError):m.inspect_channel(**args)
        args=fixture('FTNT');args['request']['url']+='&period2='
        with self.assertRaises(ValueError):m.inspect_channel(**args)
        args=fixture('FTNT');change_raw(args,lambda d:d['meta'].update(symbol='AVGO'))
        with self.assertRaises(ValueError):m.inspect_channel(**args)


if __name__=='__main__':unittest.main()
