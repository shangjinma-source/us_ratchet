import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from data.wdc_sndk_conditional_adapter import assemble_conditional_wdc, decode_daily_channel, SCOPE, BASE, PARENT, CHILD
from backtest.current_quantity_v2_next_open_book import run_next_open_book


class ConditionalAdapterTests(unittest.TestCase):
    def test_decimal_precision_and_exchange_session_date(self):
        from datetime import datetime, timezone
        stamp=int(datetime(2025,2,25,0,30,tzinfo=timezone.utc).timestamp())
        payload=dict(chart=dict(result=[dict(meta=dict(symbol='SNDK',currency='USD',instrumentType='EQUITY',
            exchangeTimezoneName='America/New_York',exchangeName='NMS'),timestamp=[stamp],
            indicators=dict(quote=[dict.fromkeys(['open','high','low','close'],['DECIMAL'])]))]))
        raw=json.dumps(payload).replace('"DECIMAL"','123.1234567890123456789012345').encode()
        rows=decode_daily_channel(raw,'SNDK')
        self.assertEqual(rows[0][0],'2025-02-24')
        self.assertEqual(rows[0][1]['close'],'123.1234567890123456789012345')
        with self.assertRaisesRegex(ValueError,'TIMEZONE'):
            decode_daily_channel(raw.replace(b'America/New_York',b'UTC'),'SNDK')

    def test_scope_and_raw_tamper(self):
        accepted=assemble_conditional_wdc(root='.')
        for damaged in (SCOPE,'data/cache/research/current_raw_capture_20261014_v1/WDC.response.bin'):
            with tempfile.TemporaryDirectory() as folder:
                root=Path(folder)
                for path in accepted['source_hashes']:
                    target=root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(Path(path).read_bytes())
                with (root/damaged).open('ab') as stream:stream.write(b'altered')
                with self.assertRaisesRegex(ValueError,'SOURCE_HASH_MISMATCH'):assemble_conditional_wdc(root=root)

    def test_ratio_guard_after_decode(self):
        original=json.loads
        def corrupt(raw,*a,**kw):
            value=original(raw,*a,**kw)
            if isinstance(value,dict) and value.get('schema')=='WDC_SNDK_DAILY_EVENT_MAPPING_CANDIDATE_V1':
                value['event_candidate']['child_ratio']='1/2'
            return value
        with patch('data.wdc_sndk_conditional_adapter.json.loads',side_effect=corrupt):
            with self.assertRaisesRegex(ValueError,'RATIO_MISMATCH'):assemble_conditional_wdc(root='.')

    def test_wi_exclusion_and_nontradable_whole_fraction_block(self):
        result=assemble_conditional_wdc(root='.')
        self.assertEqual(len(result['excluded_when_issued_sessions']),6)
        self.assertEqual(min(result['ohlc'][CHILD]),'2025-02-24')
        self.assertEqual(result['true_parent_split_events'],[])
        def book(quantity):
            return run_next_open_book(session_dates=['2025-02-20','2025-02-21','2025-02-24'],orders=[],
                initial_cash='0',initial_shares={PARENT:quantity},fee_bps='0',slippage_bps='0',
                ohlc=result['ohlc'],distribution_events=result['distribution_events'],
                distribution_fractional_cash_values=result['distribution_fractional_cash_values'],
                price_source_references={sid:[row['whole_source']] for sid,row in result['source_provenance'].items()})
        whole=book(3);fraction=book(1)
        self.assertEqual(whole['status'],'COMPLETE');self.assertEqual(whole['shares'].get(CHILD,0),0)
        self.assertEqual(whole['distribution_rights'][0]['units'],'1');self.assertFalse(whole['distribution_rights'][0]['tradable'])
        self.assertEqual(whole['cash'],'0')
        self.assertEqual(fraction['status'],'BLOCKED');self.assertEqual(fraction['last_valued_date'],'2025-02-21')
        self.assertEqual(fraction['distribution_rights'][0]['units'],'1/3')
        self.assertTrue(result['distribution_events'][0]['conditional_model'])
        self.assertFalse(result['broker_delivery_verified']);self.assertFalse(result['external_price_certified'])

if __name__=='__main__':unittest.main()
