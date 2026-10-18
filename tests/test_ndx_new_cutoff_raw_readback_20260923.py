import copy
from datetime import datetime,timezone
import gzip
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_raw_readback_20260923 as m


class RawReadbackTests(unittest.TestCase):
    def setUp(self):
        self.result = dict(meta=dict(symbol='AMAT',exchangeTimezoneName='America/New_York'),
            timestamp=[int(datetime(2026,9,day,13,30,tzinfo=timezone.utc).timestamp()) for day in (22,23)],
            indicators=dict(quote=[dict(open=[10,None],high=[11,None],low=[9,None],close=[10.5,None],volume=[100,0])],
                            adjclose=[dict(adjclose=[5.25,None])]),
            events={'splits':{'some':{'numerator':2,'denominator':1,'date':1}},'dividends':{'x':{'amount':0.1,'date':2}}})
    def raw(self,value=None):
        return json.dumps(dict(chart=dict(error=None,result=[self.result if value is None else value]))).encode()

    def test_raw_values_preserved_no_adjustment_and_receipt_filter(self):
        result=m.parse_channel(self.raw(),'AMAT','2026-09-23')
        self.assertEqual(result['last_completed_date'],'2026-09-22')
        self.assertEqual(result['completed_date_bar_count'],1)
        self.assertEqual(result['rows'][0]['raw_provider_fields']['close'],10.5)
        self.assertEqual(result['rows'][0]['raw_provider_fields']['adjclose'],5.25)
        self.assertEqual(result['raw_returned_events'],self.result['events'])
        self.assertEqual(result['rows'][1]['missing_fields'],['open','high','low','close','adjclose'])
        self.assertTrue(all(result[key] is False for key in m.FLAGS))
        self.assertEqual(m.parse_channel(gzip.compress(self.raw()),'AMAT','2026-09-23'),result)

    def test_symbol_timezone_and_duplicate_date_rejected(self):
        for key,value in [('symbol','ADI'),('exchangeTimezoneName','UTC')]:
            changed=copy.deepcopy(self.result);changed['meta'][key]=value
            with self.assertRaises(ValueError):m.parse_channel(self.raw(changed),'AMAT','2026-09-23')
        changed=copy.deepcopy(self.result);changed['timestamp'][1]=changed['timestamp'][0]+1
        with self.assertRaises(ValueError):m.parse_channel(self.raw(changed),'AMAT','2026-09-23')

    def test_numeric_and_length_corruption_rejected(self):
        for value in (True, float('nan'),-1,0):
            changed=copy.deepcopy(self.result);changed['indicators']['quote'][0]['open'][0]=value
            with self.assertRaises(ValueError):m.parse_channel(self.raw(changed),'AMAT','2026-09-23')
        changed=copy.deepcopy(self.result);changed['indicators']['quote'][0]['volume'].pop()
        with self.assertRaises(ValueError):m.parse_channel(self.raw(changed),'AMAT','2026-09-23')

    def test_naive_clock_rejected(self):
        with self.assertRaises(ValueError):m.utc('2026-09-23T04:00:00')
        m.utc('2026-09-23T04:00:00+00:00')

    def bound_fixture(self,root,alter=None):
        def save(path,value):
            raw=json.dumps(value).encode();path.write_bytes(raw)
            return hashlib.sha256(raw).hexdigest()
        source=root/'scripts'/'reader.py';source.parent.mkdir();source.write_text('fixture')
        output=root/'data/cache/research/new_cutoff_raw_capture_20260923_v1';output.mkdir(parents=True)
        template='https://query1.finance.yahoo.com/v8/finance/chart/AMAT?period1=1640995200&period2={actual_request_start_utc_epoch}&interval=1d&events=div,splits'
        epoch=int(datetime(2026,9,23,4,tzinfo=timezone.utc).timestamp())
        row=dict(ticker='AMAT',request_url_template=template,prior_url_inventory_complete=True,
                 prior_receipt={'request_url':template.format(actual_request_start_utc_epoch=epoch-1)})
        if alter=='prior_future':row['prior_receipt']['request_url']=template.format(actual_request_start_utc_epoch=epoch+1)
        plan_sha=save(output/'plan.json',dict(queue=[row]))
        started=dict(ticker='AMAT',plan_sha256=plan_sha,runner_sha256=m.RUNNER_SHA,attempt_count=1,
                     started_at_utc='2026-09-23T04:00:00+00:00',request_url=template.format(actual_request_start_utc_epoch=epoch),
                     request_method='GET',credentials_sent=False)
        if alter=='credentials':started['credentials_sent']=True
        started_sha=save(output/'AMAT.started.json',started)
        raw_path=output/'AMAT.response.bin'
        raw_path.write_bytes(gzip.compress(self.raw())[:-6] if alter=='truncated_gzip' else self.raw())
        receipt=dict(started,started_sha256=started_sha,received_at_utc='2026-09-23T04:00:01+00:00',
                     completed_training_excludes_dates_on_or_after='2026-09-23',http_status=200,final_url=started['request_url'],
                     raw_path=str(raw_path),raw_sha256=m.sha(raw_path),raw_bytes=raw_path.stat().st_size,
                     point_in_time_verified=alter=='pit',promotion_allowed=False)
        receipt_path=output/'AMAT.receipt.json';receipt_sha=save(receipt_path,receipt)
        decoded=dict(ticker='AMAT',receipt_sha256=receipt_sha,prices_reconstructed=False,cutoff_coverage_verified=False,promotion_allowed=alter=='decoded_promotion')
        decoded_path=output/'AMAT.decoded.json';decoded_sha=save(decoded_path,decoded)
        entry=dict(ticker='AMAT',receipt_path=str(receipt_path),receipt_sha256=receipt_sha,decoded_path=str(decoded_path),decoded_sha256=decoded_sha)
        index=dict(schema='NEW_CUTOFF_RAW_CAPTURE_INDEX_V1',plan_sha256=plan_sha,runner_sha256=m.RUNNER_SHA,
                   output_directory=str(output),entries=[entry],prices_reconstructed=alter=='index_upgrade',promotion_allowed=False)
        index_path=output/'index.json';index_sha=save(index_path,index)
        return source,plan_sha,index_path,index_sha

    def test_full_bound_readback_and_semantic_scope_attacks(self):
        for alteration in (None,'prior_future','credentials','pit','decoded_promotion','index_upgrade'):
            with self.subTest(alteration=alteration),tempfile.TemporaryDirectory() as folder:
                source,plan_sha,path,index_sha=self.bound_fixture(Path(folder),alteration)
                with patch.object(m,'SOURCE',source),patch.object(m,'LOADED_SHA',m.sha(source)),patch.object(m,'PLAN_SHA',plan_sha):
                    if alteration is not None:
                        with self.assertRaises(ValueError):m.build(path,index_sha)
                    else:
                        result=m.build(path,index_sha)
                        self.assertEqual(result['rows'][0]['readback_status'],'RAW_CHANNEL_READBACK_ONLY')
                        self.assertEqual(result['rows'][0]['observation']['last_completed_date'],'2026-09-22')

    def test_truncated_gzip_keeps_attempt_and_blocks_only_channel(self):
        with tempfile.TemporaryDirectory() as folder:
            source,plan_sha,path,index_sha=self.bound_fixture(Path(folder),'truncated_gzip')
            original_raw=(path.parent/'AMAT.response.bin').read_bytes()
            with patch.object(m,'SOURCE',source),patch.object(m,'LOADED_SHA',m.sha(source)),patch.object(m,'PLAN_SHA',plan_sha):
                result=m.build(path,index_sha)
            self.assertEqual(result['attempted_prefix_count'],1)
            self.assertEqual(result['rows'][0]['readback_status'],'BLOCKED_RAW_SCHEMA_NO_RETRY')
            self.assertEqual(result['rows'][0]['error_type'],'EOFError')
            self.assertEqual((path.parent/'AMAT.response.bin').read_bytes(),original_raw)


if __name__=='__main__':unittest.main()
