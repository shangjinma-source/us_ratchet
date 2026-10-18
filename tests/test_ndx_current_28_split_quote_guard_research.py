import copy,json,gzip
import unittest
from pathlib import Path
from backtest import ndx_current_28_split_quote_guard_research as module


class Tests(unittest.TestCase):
    def args(self,ticker,calendar):
        folder=module.previous.BASE/'current_22_price_capture_20260919_v1'
        receipt=json.loads((folder/(ticker+'.receipt.json')).read_bytes())
        return dict(ticker=ticker,raw_path=receipt['raw_path'],raw_sha256=receipt['raw_sha256'],calendar=calendar,quote_field_basis=module.previous.nominal.BASIS)

    def test_three_real_split_crossings_and_old_guard_unchanged(self):
        cases={'MSTR':['2024-08-07','2024-08-08'],'SHOP':['2022-06-28','2022-06-29'],'WMT':['2024-02-23','2024-02-26']}
        before=module.previous.gap.load_registry
        for ticker,dates in cases.items():
            with self.subTest(ticker=ticker):
                result=module.reconstruct_current_receipt_quote(**self.args(ticker,dates))
                rows=result['reconstruction']['rows']
                self.assertEqual([r['split_factor'] for r in rows],[3.0 if ticker=='WMT' else 10.0,1.0])
                self.assertFalse(result['point_in_time_verified'])
                with self.assertRaisesRegex(ValueError,'lacks exact supported'):
                    module.previous.reconstruct_current_receipt_quote(**self.args(ticker,dates))
        self.assertIs(module.previous.gap.load_registry,before)

    def test_wrong_ratio_day_ticker_and_unknown_extra_event(self):
        registry=module.load_registry();events=[r for r in registry['events'] if r['simple_split_guard_eligible']]
        args=self.args('MSTR',['2024-08-08']);raw=Path(args['raw_path']).read_bytes();base=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)
        for kind in ('ratio','date','ticker','extra'):
            body=copy.deepcopy(base);data=body['chart']['result'][0];mapping=data['events']['splits'];key=next(iter(mapping));event=mapping[key]
            if kind=='ratio':event.update(numerator=5,splitRatio='5:1')
            if kind=='date':
                mapping.pop(key);event['date']+=86400;mapping[str(event['date'])]=event
            if kind=='ticker':data['meta']['symbol']='WMT'
            if kind=='extra':
                other=dict(event,date=event['date']+86400);mapping[str(other['date'])]=other
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                module.previous.gap.addressed.previous.first_guard.match_returned_events(decoded=json.dumps(body).encode(),ticker='MSTR',specific_events=events,blocked_tickers=set())

    def test_all_prior_and_new_blocks_remain(self):
        for ticker in ('TRI','WDC','HONA','SNDK','FER','LRCX','LCID','EXC','HON','CMCSA'):
            with self.subTest(ticker=ticker),self.assertRaisesRegex(ValueError,'blocked|PARTITION_REQUIRED'):
                module.reconstruct_current_receipt_quote(ticker=ticker,raw_path='unused',raw_sha256='unused',calendar=['2026-09-17'],quote_field_basis=module.previous.nominal.BASIS)


if __name__=='__main__':unittest.main()
