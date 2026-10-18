from datetime import datetime
import gzip,hashlib,json
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from backtest import ndx_simple_split_quote_guard_v2_research as guard

def fixture(directory,ticker='AMZN',events=True):
    epoch=lambda day:int(datetime.fromisoformat(day).timestamp())
    times=[epoch('2022-06-03T13:30:00+00:00'),epoch('2022-06-06T13:30:00+00:00')]
    payload=dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',exchangeTimezoneName='America/New_York',instrumentType='EQUITY',dataGranularity='1d'),timestamp=times,
      indicators=dict(quote=[dict(open=[1.,2.],close=[2.,3.])]),events=dict(splits={str(times[1]):dict(date=times[1],numerator=20.,denominator=1.,splitRatio='20:1')} if events else {}))]))
    decoded=json.dumps(payload).encode();raw=gzip.compress(decoded,mtime=0);path=Path(directory)/'raw.bin';path.write_bytes(raw)
    row=dict(name='sample',raw_path=str(path.resolve()),raw_sha256=hashlib.sha256(raw).hexdigest(),raw_bytes=len(raw),decoded_sha256=hashlib.sha256(decoded).hexdigest(),
      response_headers={'Content-Encoding':'gzip'},http_status=200,request_method='GET',credentials_sent=False,
      request_url=f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1={times[0]-86400}&period2={epoch("2022-06-08T00:00:00+00:00")}&interval=1d&events=div%2Csplits',received_at_utc='2022-06-08T00:01:00+00:00')
    manifest=Path(directory)/'manifest.json';manifest.write_text(json.dumps(dict(captures=[row],source_hashes={})))
    kwargs=dict(provider_manifest_path=manifest,provider_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),capture_name='sample',ticker=ticker,calendar=['2022-06-03','2022-06-06'],quote_field_basis=guard.nominal.BASIS)
    return kwargs,row

class RegistryGuardTests(unittest.TestCase):
    def test_real_registry_exact25_and_two_identity_blocks(self):
        result=guard.registry.load_registry()
        self.assertEqual(result['event_count'],25);self.assertEqual(result['guard_eligible_event_count'],23)
        self.assertEqual({x['ticker'] for x in result['events'] if not x['simple_split_guard_eligible']},{'LCID','LRCX'})
        self.assertTrue(result['old_ftnt_8k_lacks_first_adjusted_day_new_memo_used'])

    def test_manifest_bound_gzip_preserves_share_arithmetic(self):
        with tempfile.TemporaryDirectory() as directory:
            kwargs,_=fixture(directory);result=guard.reconstruct_registry_guarded_nominal_quote(**kwargs)
            self.assertEqual([x['split_factor'] for x in result['reconstruction']['rows']],[20.,1.])
            self.assertEqual(result['known_in_request_event_dates'],['2022-06-06'])
            self.assertNotEqual(result['raw_decoding_evidence']['raw_sha256'],result['raw_decoding_evidence']['decoded_sha256'])
            self.assertFalse(result['price_identity_verified'])

    def test_omitting_known_event_cannot_become_no_action(self):
        with tempfile.TemporaryDirectory() as directory:
            kwargs,_=fixture(directory,events=False)
            with patch.object(guard.nominal,'reconstruct_nominal_quote_ticker') as old:
                with self.assertRaisesRegex(ValueError,'Known in-request'):guard.reconstruct_registry_guarded_nominal_quote(**kwargs)
                old.assert_not_called()

    def test_complex_and_identity_changes_reject_even_no_events(self):
        with tempfile.TemporaryDirectory() as directory:
            for ticker in ['LCID','LRCX','EXC','HON','AZN','SIRI','ILMN','CMCSA']:
                kwargs,_=fixture(directory,ticker,False)
                with patch.object(guard.nominal,'reconstruct_nominal_quote_ticker') as old:
                    with self.assertRaises(ValueError):guard.reconstruct_registry_guarded_nominal_quote(**kwargs)
                    old.assert_not_called()

    def test_capture_tamper_missing_receipt_and_unfinalized_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            kwargs,row=fixture(directory)
            row['received_at_utc']=None
            kwargs['provider_manifest_path'].write_text(json.dumps(dict(captures=[row])))
            with self.assertRaises(ValueError):guard.reconstruct_registry_guarded_nominal_quote(**kwargs)
            kwargs['provider_manifest_sha256']=hashlib.sha256(kwargs['provider_manifest_path'].read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,'receipt'):guard.reconstruct_registry_guarded_nominal_quote(**kwargs)
            kwargs,_=fixture(directory);kwargs['calendar']=['2022-06-07']
            with self.assertRaisesRegex(ValueError,'not certified finalized'):guard.reconstruct_registry_guarded_nominal_quote(**kwargs)

    def test_zero_event_is_only_observation_and_unknown_basis_rejects(self):
        with tempfile.TemporaryDirectory() as directory:
            kwargs,_=fixture(directory,'AMAT',False);result=guard.reconstruct_registry_guarded_nominal_quote(**kwargs)
            self.assertTrue(result['no_returned_events_observed']);self.assertFalse(result['absence_of_returned_events_proves_no_corporate_actions'])
            kwargs['quote_field_basis']='ADJCLOSE'
            with self.assertRaises(ValueError):guard.reconstruct_registry_guarded_nominal_quote(**kwargs)

if __name__=='__main__':unittest.main()
