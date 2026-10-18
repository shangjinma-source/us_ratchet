import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_current101_conditional_price_batch_20260919 as module


class Tests(unittest.TestCase):
    def test_independent_decimal_not_reported_factor(self):
        raw=json.dumps({'chart':{'result':[{'timestamp':[1723037400,1723123800],'indicators':{'quote':[{'open':[10,11],'close':[12,13]}]},'events':{'splits':{'x':{'date':1723123800,'numerator':10,'denominator':1}}}}]}}).encode()
        rows=[dict(session='2024-08-07',nominal_open=100,nominal_close=120,split_factor=999),dict(session='2024-08-08',nominal_open=11,nominal_close=13,split_factor=999)]
        self.assertEqual(module.decimal_audit(raw,rows)['maximum_absolute_error'],'0')
        for value in (True,float('nan'),float('inf'),101):
            rows[0]['nominal_open']=value
            with self.assertRaises(ValueError):module.decimal_audit(raw,rows)

    def test_saved_unindexed_ticker_rejects_before_any_recompute(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary);tasks=[{'ticker':'A'},{'ticker':'B'}]
            (output/'B.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'Unindexed'):
                module.check_output_prefix(output,[],tasks)
            (output/'B.json').unlink();(output/'A.json').write_text('{}')
            module.check_output_prefix(output,[{'ticker':'A'}],tasks)
            with self.assertRaisesRegex(ValueError,'prefix'):
                module.check_output_prefix(output,[{'ticker':'B'}],tasks)

    def test_failure_record_requires_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary);(output/'failure_A.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'failure requires'):
                module.check_output_prefix(output,[],[{'ticker':'A'}])

    def test_resigned_index_metadata_and_blocked_payload_rejected(self):
        task=dict(ticker='TRI',mode='BLOCKED_COMPLEX_OR_IDENTITY',reason='EXPLICIT_GUARD_BLOCK_NO_PRICE_OUTPUT')
        doc=dict(task,status='BLOCKED',reconstruction=None,plan_sha256='p',**{k:False for k in module.FALSE_FIELDS})
        with tempfile.TemporaryDirectory() as temporary,patch.object(module,'OUTPUT',Path(temporary)):
            path=Path(temporary)/'TRI.json';sha=module.save(path,doc)
            index=dict(schema='CURRENT101_CONDITIONAL_PRICE_INDEX_V1',plan_sha256='p',entries=[dict(ticker='TRI',mode=task['mode'],path=str(path),sha256=sha)],completed=1,planned=101,status='PARTIAL',point_in_time_verified=False,promotion_allowed=False)
            plan={'tasks':[task]};module.validate_index(index,plan,'p')
            for update in ({'completed':2},{'status':'COMPLETE'},{'promotion_allowed':True},{'schema':'FAKE'}):
                with self.assertRaises(ValueError):module.validate_index(dict(index,**update),plan,'p')
            path.unlink();doc['result']={'prices':[1]};sha=module.save(path,doc);index['entries'][0]['sha256']=sha
            with self.assertRaisesRegex(ValueError,'no price'):module.validate_index(index,plan,'p')

    def test_saved_success_must_cover_whole_receipt_completed_calendar(self):
        import copy
        probe=module.BASE/'current_receipt_quote_guard_20260919_v1/aapl_two_session_probe.json'
        result=copy.deepcopy(json.loads(probe.read_bytes()))
        result['schema']='CURRENT_RECEIPT_28_SPECIFIC_EVENT_QUOTE_GUARD_V1'
        result.update(registry_event_count=28,registry_guard_eligible_event_count=26)
        result['additional_complex_tickers_blocked']=sorted(module.guard.ADDITIONAL_BLOCKED)
        sources=result['historical_expected_source_hashes']
        module.GAP.merge(sources,{str(module.guard.SOURCE):module.guard.LOADED,str(module.guard.FACT):module.guard.FACT_SHA})
        module.GAP.attach_partition(result,sources,module.GAP.partition(sources,module.GAP.drift.load_contract(),require_all=True))
        raw=result['raw_decoding_evidence']
        task=dict(ticker='AAPL',mode='NEW_CONDITIONAL_RECONSTRUCTION',raw_path=raw['raw_path'],raw_sha256=raw['raw_sha256'],exclude_on_or_after='2026-09-18')
        document=dict(task,status='CONDITIONAL_PRICE_NOT_IDENTITY',result=result,plan_sha256='p',decimal_audit={},**{k:False for k in module.FALSE_FIELDS})
        with self.assertRaisesRegex(ValueError,'full completed calendar'):
            module.validate_saved(document,task,{'historical_expected_source_hashes':sources},'p')


if __name__=='__main__':unittest.main()
