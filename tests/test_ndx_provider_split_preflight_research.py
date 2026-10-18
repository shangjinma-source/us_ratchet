from datetime import datetime
import hashlib,json,unittest
from unittest.mock import patch
from scripts import ndx_provider_split_preflight_research as preflight

def fixture():
    times=[int(datetime.fromisoformat(x+'T13:30:00+00:00').timestamp()) for x in ['2022-06-03','2022-06-06']]
    end=int(datetime.fromisoformat('2022-06-08T00:00:00+00:00').timestamp())
    event=dict(date=times[1],numerator=20.,denominator=1.,splitRatio='20:1')
    data=dict(meta=dict(symbol='AMZN',currency='USD',exchangeTimezoneName='America/New_York',instrumentType='EQUITY',dataGranularity='1d'),timestamp=times,indicators=dict(quote=[dict(open=[1.,2.],close=[2.,3.])]),events=dict(splits={str(times[1]):event}))
    raw=json.dumps(dict(chart=dict(error=None,result=[data]))).encode()
    variant=dict(path='original.bin',sha256=hashlib.sha256(raw).hexdigest(),provider_meta=data['meta'],returned_events=dict(dividends=[],splits=[dict(provider_event_key=str(times[1]),provider_fields=event,session='2022-06-06')]))
    capture=dict(received_at_utc='2022-06-08T00:01:00+00:00',request=dict(method='GET',credentials_sent=False,url=f'https://query1.finance.yahoo.com/v8/finance/chart/AMZN?period1={times[0]-86400}&period2={end}&interval=1d&events=div%2Csplits'))
    return dict(raw=raw,ticker='AMZN',variant=variant,original_capture=capture,requirements={'2023-04-03':{'2022-06-03','2022-06-06'}},events=[dict(ticker='AMZN',first_adjusted_trading_date='2022-06-06',new_shares=20,old_shares=1,specific_simple_share_split_event_supported=True)])

class PreflightTests(unittest.TestCase):
    def test_only_preflight_no_price_generation_and_name_gap_visible(self):
        with patch.object(preflight.nominal,'reconstruct_nominal_quote_ticker',side_effect=AssertionError('must not reconstruct')):
            result=preflight.analyze_raw(**fixture())
        self.assertTrue(result['technical_simple_split_preflight_passed']);self.assertFalse(result['guard_v2_capture_name_addressable'])
        self.assertFalse(result['price_reconstruction_admitted']);self.assertFalse(result['explicit_basis_independently_authenticated'])

    def test_receipt_missing_preserved_not_replaced_with_saved_time(self):
        params=fixture();params['original_capture']['received_at_utc']=None;params['original_capture']['response_saved_at_utc']='2022-06-08T00:01:00+00:00'
        result=preflight.analyze_raw(**params)
        self.assertIn('EXACT_RECEIPT_MISSING',result['technical_blockers']);self.assertTrue(result['full_applicable_history_present'])
        self.assertIsNone(preflight.choose_candidate([result]))

    def test_previous_close_gap_and_known_split_deletion(self):
        params=fixture();params['requirements']['2023-04-03'].add('2022-06-02');result=preflight.analyze_raw(**params)
        self.assertEqual(result['missing_open_close_occurrences'],2)
        params=fixture();document=json.loads(params['raw']);document['chart']['result'][0]['events']={};params['raw']=json.dumps(document).encode();params['variant']['returned_events']['splits']=[]
        result=preflight.analyze_raw(**params)
        self.assertTrue(any(x.startswith('KNOWN_EVENT_DENOMINATOR_OR_FACT_MISMATCH') for x in result['technical_blockers']))

    def test_horizon_not_received_day_and_source_index_contradiction(self):
        params=fixture();params['original_capture']['received_at_utc']='2026-09-11T21:00:00+00:00'
        self.assertIn('EVENT_HORIZON_NOT_RECEIPT_MARKET_DATE',preflight.analyze_raw(**params)['technical_blockers'])
        params=fixture();params['variant']['returned_events']['splits']=[]
        with self.assertRaisesRegex(ValueError,'event facts differ'):preflight.analyze_raw(**params)

if __name__=='__main__':unittest.main()
