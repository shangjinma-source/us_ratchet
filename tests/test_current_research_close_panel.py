from datetime import datetime, timezone
import gzip
import json
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from data.current_research_close_panel import (
    bind_observed_close_panel, load_current_close_panel, parse_provider_channel,
)
from data import current_research_close_panel as adapter


def channel(ticker, dates, closes=None):
    stamps=[int(datetime.fromisoformat(day+'T14:00:00+00:00').timestamp()) for day in dates]
    raw=json.dumps({'chart':{'error':None,'result':[{
        'meta':{'symbol':ticker,'currency':'USD','instrumentType':'ETF' if ticker in ('QQQ','SPY') else 'EQUITY',
                'exchangeTimezoneName':'America/New_York','dataGranularity':'1d'},
        'timestamp':stamps,'indicators':{'quote':[{'close':closes if closes is not None else [10+i for i in range(len(dates))]}]},
        'events':{'splits':{'old':{'date':123,'numerator':2,'denominator':1}},'dividends':{}},
    }]}}).encode()
    return parse_provider_channel(raw,ticker,control=ticker in ('TSM','QQQ','SPY'))


class CurrentResearchClosePanelTests(unittest.TestCase):
    def test_alignment_keeps_prefix_holes_null_and_future_exclusion(self):
        dates=['2026-10-07','2026-10-08','2026-10-09','2026-10-12']
        channels={t:channel(t,dates) for t in ('QQQ','SPY','TSM')}
        channels['AAA']=channel('AAA',['2026-10-08','2026-10-12','2026-10-13'],[12,14,99])
        channels['BBB']=channel('BBB',dates,[10,None,12,13])
        reference={'AAA':{'path':'old_inventory.json','sha256':'a'*64,'json_pointer':'/rows/0'}}
        result=bind_observed_close_panel(observed_symbols=['AAA','BBB'],channels=channels,history_sessions=4,target='2026-10-12',metadata_references=reference)
        first,second=result['stocks']
        self.assertEqual(result['calendar'],dates)
        self.assertEqual(first['raw_close'],[None,12,None,14])
        self.assertEqual(first['unavailable_prefix_sessions'],1)
        self.assertEqual(first['missing_dates'],['2026-10-07','2026-10-09'])
        self.assertEqual(first['excluded_future_dates'],['2026-10-13'])
        self.assertEqual(second['null_close_dates'],['2026-10-08'])
        self.assertFalse(first['numerical_history_complete'])
        self.assertEqual(first['old_coordinate_risk_and_gap_reference'],reference['AAA'])
        self.assertEqual(first['events_reference']['splits_count'],1)
        self.assertFalse(result['quote_basis_authenticated'])

    def test_all101_kept_controls_separate_and_no_automatic_qualification(self):
        dates=['2026-10-09','2026-10-12'];stocks=['STK'+str(i) for i in range(101)]
        channels={t:channel(t,dates) for t in stocks+['TSM','QQQ','SPY']}
        result=bind_observed_close_panel(observed_symbols=stocks,channels=channels,history_sessions=2)
        self.assertEqual([r['ticker'] for r in result['stocks']],stocks)
        self.assertEqual([r['ticker'] for r in result['controls']],['TSM','QQQ','SPY'])
        self.assertTrue(all(r['numerical_history_complete'] for r in result['stocks']))
        self.assertTrue(all(not r['qualified'] and not r['current_risk_interval_verified'] for r in result['stocks']))
        self.assertEqual(result['price_intervals'],1)
        with self.assertRaises(ValueError):
            bind_observed_close_panel(observed_symbols=stocks+['QQQ'],channels=channels,history_sessions=2)
        with self.assertRaises(ValueError):
            bind_observed_close_panel(observed_symbols=stocks,channels=channels,history_sessions=253)

    def test_default_prepare_reads_nothing_and_bad_raw_rejected(self):
        with patch('pathlib.Path.open',side_effect=AssertionError('unexpected actual read')):
            prepared=load_current_close_panel()
            self.assertEqual(prepared['status'],'PREPARED_NOT_EXTRACTED')
            self.assertEqual(prepared['minimum_feature_history_sessions'],253)
            self.assertEqual(prepared['calendar_scope'],'ALL_QQQ_OBSERVED_COMPLETED_DATES')
            self.assertEqual(prepared['file_reads'],0)
        with self.assertRaises(ValueError):parse_provider_channel(b'{"chart":1,"chart":2}','AAA')
        with self.assertRaises(ValueError):parse_provider_channel(b'{"chart":NaN}','AAA')
        for closes in ([True,10],[float('nan'),10],[float('inf'),10],[0,10]):
            with self.assertRaises(ValueError):channel('AAA',['2026-10-09','2026-10-12'],closes)
        with self.assertRaises(ValueError):channel('AAA',['2026-10-12','2026-10-12'])

    def test_regular_path_hash_bounds_and_real_symlink_protection(self):
        with TemporaryDirectory() as directory:
            source=Path(directory)/'source.json';source.write_bytes(b'{}');sha=hashlib.sha256(b'{}').hexdigest()
            self.assertEqual(adapter._read_fixed(source,sha),b'{}')
            with self.assertRaises(ValueError):adapter._read_fixed(source,'0'*64)
            with patch.object(adapter,'MAX_BYTES',1),self.assertRaises(ValueError):adapter._read_fixed(source,sha)
            linked=Path(directory)/'linked.json'
            try:linked.symlink_to(source)
            except OSError as error:self.skipTest('symlink not available: '+str(error))
            with self.assertRaises(ValueError):adapter._read_fixed(linked,sha)


if __name__=='__main__':unittest.main()
