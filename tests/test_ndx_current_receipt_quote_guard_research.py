import json
from pathlib import Path
import tempfile
import unittest
from backtest import ndx_current_receipt_quote_guard_research as module


class Tests(unittest.TestCase):
    def args(self):
        folder=module.BASE/'current79_new_asof_capture_20260919_v1'
        receipt=json.loads((folder/'AAPL.receipt.json').read_bytes())
        return dict(ticker='AAPL',raw_path=receipt['raw_path'],raw_sha256=receipt['raw_sha256'],calendar=['2026-09-16','2026-09-17'],quote_field_basis=module.nominal.BASIS)

    def test_real_receipt_chain_and_conditional_small_reconstruction(self):
        result=module.reconstruct_current_receipt_quote(**self.args())
        self.assertEqual(len(result['reconstruction']['rows']),2)
        self.assertEqual(result['provider_metadata']['symbol'],'AAPL')
        self.assertFalse(result['price_identity_verified'])
        self.assertFalse(result['historical_full_source_closure_verified'])
        self.assertNotIn('source_hashes',result)
        self.assertEqual(len(result['historical_price_cache_gap_observations']),26)

    def test_partition_and_complex_block_even_after_requesting_late_calendar(self):
        for ticker in ('HONA','SNDK','FER','LCID','LRCX','HON','EXC'):
            with self.subTest(ticker=ticker),self.assertRaisesRegex(ValueError,'PARTITION_REQUIRED|blocked'):
                module.reconstruct_current_receipt_quote(**dict(self.args(),ticker=ticker))

    def test_raw_redirect_rehash_and_wrong_hash_rejected(self):
        args=self.args()
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'AAPL.response.bin';path.write_bytes(Path(args['raw_path']).read_bytes())
            with self.assertRaisesRegex(ValueError,'original ticker address'):
                module.load_capture(ticker='AAPL',raw_path=str(path),raw_sha256=args['raw_sha256'],sources={})
        with self.assertRaisesRegex(ValueError,'binding differs'):
            module.load_capture(ticker='AAPL',raw_path=args['raw_path'],raw_sha256='0'*64,sources={})

    def test_receipt_day_duplicate_unknown_basis_rejected(self):
        for changes in ({'calendar':['2026-09-18']},{'calendar':['2026-09-17','2026-09-17']},{'quote_field_basis':'UNKNOWN'},{'calendar':[True]}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                module.reconstruct_current_receipt_quote(**dict(self.args(),**changes))

    def test_nominal_metadata_and_finite_guards_are_preserved(self):
        args=self.args()
        raw,receipt,request,_=module.load_capture(ticker='AAPL',raw_path=args['raw_path'],raw_sha256=args['raw_sha256'],sources={})
        for field,value in [('symbol','SPCX'),('currency','EUR'),('instrumentType','ETF')]:
            body=json.loads(raw);body['chart']['result'][0]['meta'][field]=value
            with self.assertRaisesRegex(ValueError,'coordinates differ'):
                module.nominal.reconstruct_nominal_quote_ticker(raw=json.dumps(body).encode(),ticker='AAPL',calendar=args['calendar'],request=request,received_at_utc=receipt['received_at_utc'],quote_field_basis=args['quote_field_basis'])
        body=json.loads(raw);body['chart']['result'][0]['indicators']['quote'][0]['open'][0]=None
        with self.assertRaisesRegex(ValueError,'Finite positive'):
            module.nominal.reconstruct_nominal_quote_ticker(raw=json.dumps(body).encode(),ticker='AAPL',calendar=args['calendar'],request=request,received_at_utc=receipt['received_at_utc'],quote_field_basis=args['quote_field_basis'])


if __name__=='__main__':unittest.main()
