"""Read-only hard-artifact fixtures; no publication, HTTP, fit, or source authentication."""
import gzip
import hashlib
import json
from pathlib import Path
from decimal import Decimal,localcontext
import unittest
from backtest import ndx_conditional_channel_input_research as m

BASE=Path(__file__).resolve().parents[1]/'data/cache/research'
INVENTORY=BASE/'current99_conditional_price_inventory_20260919_v1/inventory.json'
INVENTORY_SHA='59ebaf50fdf35c6c390a747de026bc353200f64525b9c30f3e14d935aba209f3'
READINESS=BASE/'latest_conditional_input_readiness_20260919_v1/readiness.json'
READINESS_SHA='b3a215d05cfb085c4637713d65fb86d565def48728cb382efe94ad1e206d3c49'


def read(path,sha,decode=True):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Actual fixture changed')
    return json.loads(raw) if decode else raw


def fixture(ticker):
    inventory=read(INVENTORY,INVENTORY_SHA);reference=read(READINESS,READINESS_SHA)['observed_reference_calendar'][-127:]
    item=next(r for r in inventory['rows'] if r['ticker']==ticker)
    selected=item['post_action_reference'] or item['original_reference'];ref=selected['artifact_reference'];doc=read(ref['path'],ref['sha256'])
    if ticker=='EXC':
        result=doc['result'];rawref=doc['raw_decoding_evidence'];rows=[]
        for row in result['rows']:
            converted=dict(row,split_factor=row['factor'],split_factor_numerator=row['factor_numerator'],split_factor_denominator=row['factor_denominator'],later_split_effective_sessions=row['returned_later_split_like_events'])
            rows.append(converted)
        exclude=result['incomplete_receipt_day_excluded'];floor=selected['first_session']
    else:
        rows=doc['result']['reconstruction']['rows'];rawref={'raw_path':doc['raw_path'],'raw_sha256':doc['raw_sha256']};exclude=doc['exclude_on_or_after'];floor=None
    raw=read(rawref['raw_path'],rawref['raw_sha256'],False)
    policies=[dict(session=e['session'],numerator=e['numerator'],denominator=e['denominator'],kind='BEFORE_PARTITION_UNMODELLED' if ticker=='EXC' else 'ORDINARY_SPLIT') for e in item['original_reference']['returned_split_events']]
    return dict(ticker=ticker,raw_bytes=raw,quote_rows=rows,calendar=reference,cutoff='2026-09-17',exclude_on_or_after=exclude,event_policy=policies,regular_floor=floor)


class ActualFixtureTests(unittest.TestCase):
    def test_six_hard_raw_quote_pairs_with_independent_return_arithmetic(self):
        for ticker in ('KLAC','BKNG','MNST','CRWD','CDNS','EXC'):
            with self.subTest(ticker=ticker):
                args=fixture(ticker);result=m.build_channel_input(**args)
                raw=args['raw_bytes'];decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
                data=json.loads(decoded,parse_float=Decimal)['chart']['result'][0]
                closes={m._session(stamp):Decimal(str(close)) for stamp,close in zip(data['timestamp'],data['indicators']['quote'][0]['close'])}
                with localcontext() as context:
                    context.prec=50
                    for row in result['price_returns']:
                        expected=closes[row['session']]/closes[row['previous_session']]-1
                        self.assertLessEqual(abs(Decimal(str(row['price_return']))-expected),Decimal('1e-14'))
                self.assertEqual(len(result['price_returns']),126)
                self.assertFalse(result['security_identity_verified'])
                self.assertFalse(result['legal_training_input_admitted'])
                self.assertEqual(result['liquidity']['status'],'BLOCKED_VOLUME_UNIT_UNKNOWN' if ticker in ('MNST','CRWD') else 'CONDITIONAL_RAW_VOLUME_TIMES_NOMINAL_CLOSE')
                self.assertTrue(all(type(d) is str for r in args['quote_rows'] for d in r['later_split_effective_sessions']))
                self.assertEqual(json.loads(json.dumps(result,allow_nan=False))['returned_events'],json.loads(decoded)['chart']['result'][0].get('events',{}))
                if ticker=='EXC':
                    self.assertEqual(result['regular_floor'],'2022-02-02')
                    self.assertEqual(result['event_policy'][0]['kind'],'BEFORE_PARTITION_UNMODELLED')


if __name__=='__main__':unittest.main()
