from datetime import date, timedelta
import unittest

from data.current_research_close_panel import bind_observed_close_panel, load_current_close_panel


def simple_channel(ticker, dates):
    return dict(ticker=ticker,dates=dates,closes=[100+index for index in range(len(dates))],
                control=ticker in ('TSM','QQQ','SPY'),raw_sha256='a'*64,decoded_sha256='b'*64,
                events_sha256='c'*64,splits_payload_sha256='d'*64,dividends_payload_sha256='e'*64,
                splits_count=0,dividends_count=0)


class CurrentCloseFullPrefixTests(unittest.TestCase):
    def test_full_calendar_retains337_diagnostic_prefix_and_future_exclusion(self):
        # Synthetic observation dates test alignment, not an exchange calendar.
        start=date(2025,10,1);dates=[(start+timedelta(days=index)).isoformat() for index in range(380)]
        target=dates[-2];full=dates[:-1]
        channels={ticker:simple_channel(ticker,dates) for ticker in ('AAA','TSM','QQQ','SPY')}
        channels['SHORT']=simple_channel('SHORT',dates[100:])
        result=bind_observed_close_panel(observed_symbols=['AAA','SHORT'],channels=channels,target=target)
        self.assertEqual(result['calendar'],full)
        self.assertEqual(result['observation_sessions'],379)
        self.assertEqual(result['price_intervals'],378)
        self.assertEqual(result['calendar_scope'],'ALL_QQQ_OBSERVED_COMPLETED_DATES')
        self.assertEqual(len(result['stocks'][0]['raw_close'][:-84]),295)
        self.assertEqual(len(result['stocks'][0]['raw_close'][-337:]),337)
        self.assertEqual(result['stocks'][1]['raw_close'][:100],[None]*100)
        self.assertEqual(result['stocks'][1]['unavailable_prefix_sessions'],100)
        self.assertEqual(result['stocks'][1]['excluded_future_dates'],[dates[-1]])
        self.assertEqual([row['ticker'] for row in result['controls']],['TSM','QQQ','SPY'])
        self.assertFalse(result['fit_performed'])

    def test_full_calendar_ceiling_and_prepare_metadata(self):
        prepared=load_current_close_panel()
        self.assertEqual(prepared['maximum_calendar_sessions'],20000)
        self.assertEqual(prepared['file_reads'],0)
        start=date(1970,1,1);dates=[(start+timedelta(days=index)).isoformat() for index in range(20001)]
        channels={ticker:simple_channel(ticker,dates) for ticker in ('AAA','TSM','QQQ','SPY')}
        with self.assertRaises(ValueError):
            bind_observed_close_panel(observed_symbols=['AAA'],channels=channels,target=dates[-1])


if __name__=='__main__':unittest.main()
