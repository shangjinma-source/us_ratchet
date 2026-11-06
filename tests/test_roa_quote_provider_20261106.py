import json
import unittest
from datetime import datetime, timedelta, timezone
from data.roa_quote_provider import RoaQuoteProvider


class QuoteTests(unittest.TestCase):
    def setUp(self):
        self.open = datetime(2026,11,6,14,30,tzinfo=timezone.utc)
        self.now = self.open + timedelta(minutes=2)
        self.payload = {'chart': {'error': None, 'result': [{
            'meta': {'symbol':'TEST','currency':'USD','exchangeTimezoneName':'America/New_York',
                     'dataGranularity':'1m','regularMarketPrice':101,
                     'regularMarketTime':int(self.now.timestamp()),
                     'currentTradingPeriod':{'regular':{'start':int(self.open.timestamp()),
                                                       'end':int((self.open+timedelta(hours=6,minutes=30)).timestamp())}}},
            'timestamp':[int(self.open.timestamp()),int(self.open.timestamp())+60],
            'indicators':{'quote':[{'open':[99,100],'high':[102,102],'low':[98,99],
                                    'close':[100,101],'volume':[10,12]}]}}]}}
        self.calls = 0
        def fetch(ticker):
            self.calls += 1
            return json.dumps(self.payload).encode()
        self.provider = RoaQuoteProvider(identity_map={'sid':{'ticker':'TEST'}},
            session_reader=lambda day:dict(open_at=self.open,close_at=self.open+timedelta(hours=6,minutes=30)),
            limit_builder=lambda last,phase:dict(buy=last,sell=last),fetch=fetch,clock=lambda:self.now)

    def run_quote(self):
        return self.provider({},['sid'],'2026-11-06','OPEN',self.now)

    def test_open_is_not_last_and_debounce(self):
        result=self.run_quote()
        self.assertEqual(result['opening_prices']['sid'],'99')
        self.assertEqual(result['marks']['sid']['price'],'101')
        self.run_quote()
        self.assertEqual(self.calls,1)

    def test_premarket_no_fetch(self):
        self.now=self.open-timedelta(minutes=1)
        with self.assertRaisesRegex(ValueError,'WAIT_FRESH_QUOTE'): self.run_quote()
        self.assertEqual(self.calls,0)

    def test_missing_open_no_substitute(self):
        self.payload['chart']['result'][0]['indicators']['quote'][0]['open'][0]=None
        with self.assertRaisesRegex(ValueError,'OPENING_PRICES_UNAVAILABLE'):self.run_quote()

    def test_stale_last_rejected(self):
        self.payload['chart']['result'][0]['meta']['regularMarketTime']=int(self.open.timestamp())
        self.now+=timedelta(seconds=1)
        with self.assertRaisesRegex(ValueError,'WAIT_FRESH_QUOTE'):self.run_quote()

    def test_open_bar_without_trades_rejected(self):
        self.payload['chart']['result'][0]['indicators']['quote'][0]['volume'][0]=0
        with self.assertRaisesRegex(ValueError,'OPENING_PRICES_UNAVAILABLE'):self.run_quote()

    def test_identity_rejected(self):
        self.payload['chart']['result'][0]['meta']['symbol']='OTHER'
        with self.assertRaisesRegex(ValueError,'WAIT_FRESH_QUOTE'):self.run_quote()

    def test_wrong_session_bounds(self):
        self.payload['chart']['result'][0]['meta']['currentTradingPeriod']['regular']['end']-=60
        with self.assertRaisesRegex(ValueError,'WAIT_FRESH_QUOTE'):self.run_quote()

    def test_disjoint_ten_old_ten_new_domain(self):
        identities={str(i):{'ticker':'TEST'} for i in range(20)}
        self.provider.identities=identities
        result=self.provider({},list(identities),'2026-11-06','OPEN',self.now)
        self.assertEqual(len(result['marks']),20)
        with self.assertRaisesRegex(ValueError,'QUOTE_IDENTITY_DOMAIN_MISMATCH'):
            self.provider({},['not_server_bound'],'2026-11-06','OPEN',self.now)


if __name__=='__main__': unittest.main()
