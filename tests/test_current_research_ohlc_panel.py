from copy import deepcopy
from datetime import datetime
import json
from unittest.mock import patch
import unittest

from data import current_research_ohlc_panel as panel
from data import current_research_close_panel as close


DATES=['2026-10-09','2026-10-12']


def parse(ticker,dates=DATES,values=None):
    values=values if values is not None else [[10,12,9,11,100] for day in dates]
    raw=json.dumps({'chart':{'error':None,'result':[{
        'meta':{'symbol':ticker,'currency':'USD','instrumentType':'ETF' if ticker in ('QQQ','SPY') else 'EQUITY',
                'exchangeTimezoneName':'America/New_York','dataGranularity':'1d'},
        'timestamp':[int(datetime.fromisoformat(day+'T14:00:00+00:00').timestamp()) for day in dates],
        'indicators':{'quote':[{field:[row[index] for row in values] for index,field in enumerate(panel.FIELDS)}]},
        'events':{'splits':{},'dividends':{}},
    }]}}).encode()
    return panel.parse_provider_ohlc(raw,ticker)


def fixture(stocks=('AAA',)):
    channels={ticker:parse(ticker) for ticker in list(stocks)+list(close.CONTROLS)}
    sealed={'calendar':list(DATES),'target':DATES[-1],
            'stocks':[{'ticker':ticker,'raw_close':[11,11]} for ticker in stocks],
            'controls':[{'ticker':ticker,'raw_close':[11,11]} for ticker in close.CONTROLS],**close.FALSE_FLAGS}
    return sealed,channels


class CurrentOhlcPanelTests(unittest.TestCase):
    def test_alignment_missing_open_history_future_and_controls(self):
        sealed,channels=fixture(('AAA','SHORT'))
        channels['AAA']=parse('AAA',DATES+['2026-10-13'],[[None,12,9,11,100],[10,12,9,11,100],[20,22,19,21,200]])
        channels['SHORT']=parse('SHORT',[DATES[-1]])
        sealed['stocks'][1]['raw_close']=[None,11]
        result=panel.bind_ohlc_panel(sealed_close=sealed,channels=channels)
        self.assertEqual(result['fields'],['open','high','low','close','volume'])
        self.assertEqual(result['stocks'][0]['values'][0],[None,12,9,11,100])
        self.assertEqual(result['stocks'][0]['missing_open_indices'],[0])
        self.assertEqual(result['stocks'][0]['excluded_future_dates'],['2026-10-13'])
        self.assertEqual(result['stocks'][1]['values'][0],[None]*5)
        self.assertEqual([row['ticker'] for row in result['controls']],list(close.CONTROLS))
        self.assertFalse(result['open_execution_authorized'])
        self.assertFalse(result['economic_total_return'])

    def test_bad_dimensions_nonfinite_partial_relations_and_iso_rejected(self):
        for values in ([[None,8,9,10,100],[10,12,9,11,100]],
                       [[None,12,9,13,100],[10,12,9,11,100]],
                       [[8,None,9,None,100],[10,12,9,11,100]],
                       [[float('nan'),12,9,11,100],[10,12,9,11,100]]):
            with self.subTest(values=values),self.assertRaises(ValueError):parse('AAA',values=values)
        sealed,channels=fixture()
        channels['AAA']['dates'][0]='2026-10-09T00:00:00'
        with self.assertRaises(ValueError):panel.bind_ohlc_panel(sealed_close=sealed,channels=channels)
        sealed,channels=fixture();channels['AAA']['values'][0]=[10,12,9,11]
        with self.assertRaises(ValueError):panel.bind_ohlc_panel(sealed_close=sealed,channels=channels)
        # A partial bar with consistent known bounds is retained, not invented.
        self.assertIsNone(parse('AAA',values=[[None,12,9,11,100],[10,12,9,11,100]])['values'][0][0])

    def test_exact_close_match_all101_and_default_no_reads(self):
        names=['STK'+str(index) for index in range(101)];sealed,channels=fixture(names)
        result=panel.bind_ohlc_panel(sealed_close=sealed,channels=channels)
        self.assertEqual([row['ticker'] for row in result['stocks']],names)
        self.assertTrue(all(row['close_matches_sealed_values'] for row in result['stocks']))
        changed=deepcopy(sealed);changed['stocks'][0]['raw_close'][0]=11.0
        with self.assertRaises(ValueError):panel.bind_ohlc_panel(sealed_close=changed,channels=channels)
        changed=deepcopy(sealed);changed['stocks'][0]['raw_close'][0]=12
        with self.assertRaises(ValueError):panel.bind_ohlc_panel(sealed_close=changed,channels=channels)
        with patch('pathlib.Path.open',side_effect=AssertionError('unexpected IO')),patch.object(close,'load_current_close_panel',side_effect=AssertionError('duplicate extraction')):
            prepared=panel.load_current_ohlc_panel()
            self.assertEqual(prepared['source_files_read'],0)
            self.assertEqual(prepared['status'],'PREPARED_NOT_EXTRACTED')


if __name__=='__main__':unittest.main()
