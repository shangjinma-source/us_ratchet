from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_equal_weight_base_report as report
from test_ndx_joint_weight_evaluation import fixture
from backtest.ndx_dynamic_training_semantics import training_semantics


class EqualBaseReportTests(unittest.TestCase):
    def synthetic_report(self):
        _,inputs=fixture();combo=(sorted(inputs['universe'].ticker)[0],)
        semantics=training_semantics(inputs=inputs,decision_data_end=str(inputs['returns'].index[-1].date()),
                                    source_batch='SYNTHETIC',universe_track='strict_technology')
        prepared=dict(inputs=inputs,combinations=[combo],source_hashes={},training_semantics=semantics,
            summary=dict(equal_weight_base_count=1,all_base_count=1,delta_count=0,cardinalities=[1],
                saved_economic_metrics_used=False,new_evaluation_performed=False,promotion_allowed=False))
        with patch.object(report.preparation,'prepare_equal_base_date',return_value=prepared):
            return report.run(source_batch='SYNTHETIC',universe_track='strict_technology',selection_date='2020-09-10')

    def test_exclusive_save_strict_readback_and_no_real_prepare(self):
        value=self.synthetic_report()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'report.json';digest=report.save_new(value,path)
            self.assertEqual(report.load_report(path,expected_sha256=digest),value)
            with self.assertRaises(FileExistsError):report.save_new(value,path)
            with self.assertRaises(ValueError):report.load_report(path,expected_sha256='0'*64)

    def test_identity_count_wholelot_and_missing_source_rejected(self):
        value=self.synthetic_report()
        for mutation in ('count','identity','wholelot','source','risk_empty','risk_bool','semantics'):
            altered=deepcopy(value)
            if mutation=='count':altered['evaluation']['count']=2
            if mutation=='identity':altered['evaluation']['records'][0]['tickers']='WRONG'
            if mutation=='wholelot':altered['evaluation']['records'][0]['whole_lot_status']='PASSED'
            if mutation=='source':altered['source_hashes'].pop(str(report._SOURCE))
            if mutation=='risk_empty':altered['evaluation']['records'][0]['risk_liquidity_metrics']={}
            if mutation=='risk_bool':altered['evaluation']['records'][0]['risk_liquidity_metrics']['declared_max_single_passed']=1
            if mutation=='semantics':altered['training_semantics']['payload']['source_batch']='wrong'
            with self.assertRaises(ValueError):report._validate(altered)

    def test_rehashed_invalid_payload_still_fails_validation(self):
        value=self.synthetic_report();value['evaluation']['records'][0]['holding_count']=True
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'bad.json';raw=json.dumps(value).encode();path.write_bytes(raw)
            with self.assertRaises(ValueError):report.load_report(path,expected_sha256=hashlib.sha256(raw).hexdigest())


if __name__=='__main__':unittest.main()
