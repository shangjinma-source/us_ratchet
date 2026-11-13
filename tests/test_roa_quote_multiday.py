import json
import unittest
from datetime import timedelta
from unittest.mock import patch, MagicMock
from data import roa_quote_provider as quotes
from test_roa_quote_provider_20261106 import QuoteTests as Fixture

class MultidayQuoteTests(unittest.TestCase):
    def test_previous_days_do_not_replace_current_open(self):
        fixture = Fixture(); fixture.setUp()
        result = fixture.payload['chart']['result'][0]
        result['timestamp'].insert(0, int((fixture.open-timedelta(days=1)).timestamp()))
        for key, value in [('open', 5), ('high', 6), ('low', 4), ('close', 5), ('volume', 100)]:
            result['indicators']['quote'][0][key].insert(0, value)
        self.assertEqual(fixture.run_quote()['opening_prices']['sid'], '99')
        result['indicators']['quote'][0]['volume'][1] = 0
        with self.assertRaisesRegex(ValueError, 'OPENING_PRICES_UNAVAILABLE'):
            fixture.provider.cache.clear(); fixture.run_quote()

    def test_bounded_five_day_raw_response(self):
        response = MagicMock(); response.__enter__.return_value = response
        response.read.return_value = b'unchanged vendor response'
        with patch.object(quotes, 'urlopen', return_value=response) as request:
            self.assertEqual(quotes.fetch_intraday_chart('ODFL'), b'unchanged vendor response')
            self.assertTrue(request.call_args.args[0].full_url.endswith('interval=1m&range=5d'))
            self.assertEqual(request.call_args.kwargs['timeout'], 10)
            response.read.assert_called_once_with(4*1024*1024+1)

if __name__ == '__main__': unittest.main()
