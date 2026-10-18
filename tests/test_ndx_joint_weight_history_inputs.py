import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from backtest.ndx_joint_weight_history_inputs import (
    _Sources, _rules, _rule_for, _stitch, prepare_joint_weight_history_inputs)
from test_ndx_joint_weight_evaluation import fixture


class HistoryInputsTests(unittest.TestCase):
    def test_source_change_is_rejected_even_when_revised_is_allowed(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.csv'
            first=b'Date,Close\n2020-01-01,1\n'
            descriptor=dict(path=str(path),sha256=hashlib.sha256(first).hexdigest())
            path.write_bytes(first)
            sources=_Sources()
            sources.read(descriptor)
            path.write_bytes(b'Date,Close\n2020-01-01,2\n')
            with self.assertRaisesRegex(ValueError,'Source changed'):
                sources.read(descriptor,revised=True)
            with self.assertRaisesRegex(ValueError,'Source changed'):
                sources.validate_unchanged()

    def test_duplicate_csv_headers_and_invalid_contract_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bad.csv'
            raw=b'Date,Close,Close\n2020-01-01,1,2\n'
            path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, 'Duplicate source columns'):
                _Sources().csv(dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest()))
            contract=fixture()[1]['contract']
            contract['portfolio_cash_usd']=-1
            with self.assertRaisesRegex(ValueError, 'Invalid evaluation capital'):
                prepare_joint_weight_history_inputs(path,'0'*64,evaluation_contract=contract,
                    training_lookback_days=504,minimum_price_rows_before_selection=252)

    def test_exact_prefix_and_explicit_revision_are_distinct(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'returns.csv'
            original = b'Date,Close\n2020-01-01,1\n'
            descriptor = dict(path=str(path), sha256=hashlib.sha256(original).hexdigest())
            path.write_bytes(original+b'2020-01-02,2\n')
            sources = _Sources()
            self.assertEqual(sources.read(descriptor, prefix=True), original)
            self.assertEqual(sources.evidence[-1]['status'], 'EXACT_PREFIX')
            path.write_bytes(b'Date,Close\n2020-01-01,3\n')
            sources = _Sources()
            with self.assertRaises(ValueError):
                sources.read(descriptor, prefix=True)
            sources.read(descriptor, prefix=True, revised=True)
            self.assertEqual(sources.evidence[-1]['status'], 'REVISED_RETURN_DATA_NEW_EXPERIMENT')

    def test_cross_ticker_intervals_identity_and_duplicate_dates(self):
        raw = b'''schema_version: 1
rules:
  - rule_id: alias
    cik: '0000000001'
    cusip: ABC123456
    recognized_tickers: [OLD, NEW]
    intervals:
      - {effective_from: null, effective_to: '2020-01-02', price_ticker: OLD}
      - {effective_from: '2020-01-03', effective_to: null, price_ticker: NEW}
'''
        rules = _rules(raw)
        selection = pd.Timestamp('2020-01-05')
        rule = _rule_for('security:0000000001:ABC123456', 'NEW', selection, rules)
        old = pd.DataFrame({'Close':[1.,2.,99.]}, index=pd.date_range('2020-01-01', periods=3))
        new = pd.DataFrame({'Close':[99.,3.,4.]}, index=pd.date_range('2020-01-02', periods=3))
        stitched = _stitch([('OLD',old),('NEW',new)], rule, selection)
        self.assertEqual(stitched.Close.tolist(), [1.,2.,3.,4.])
        with self.assertRaises(ValueError):
            _rule_for('security:0000000001:WRONGCUSI', 'NEW', selection, rules)
        with self.assertRaises(ValueError):
            _stitch([('OLD',old),('OLD',old)], rule, selection)

    def test_full_preparation_keeps_pool_incumbent_and_exact_calendar(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def put(name, value):
                p=root/name; p.parent.mkdir(parents=True,exist_ok=True)
                raw=value.encode() if isinstance(value,str) else json.dumps(value).encode()
                p.write_bytes(raw)
                return dict(path=str(p),sha256=hashlib.sha256(raw).hexdigest())
            csv='Date,Close,Volume\n2020-01-01,10,100\n2020-01-02,11,100\n2020-01-03,12,100\n2020-01-06,13,100\n'
            price=put('A.csv',csv)
            nav=put('nav.csv',csv)
            member=put('members.csv','selection_date,universe_track,membership_window_eligible,ticker,security_id,issuer_id,risk_chain\n2020-01-07,strict_technology,True,A,security:0000000002:ABC123456,issuer:0000000002,tech\n')
            membership=put('membership.csv','selection_date,universe_track,security_id,input_ready\n2020-01-07,strict_technology,security:0000000002:ABC123456,True\n')
            identity=put('identity.csv','identity_status,issuer_ids\nIDENTITY_MATCH,issuer:0000000002\n')
            lifecycle=put('lifecycle.yaml','schema_version: 1\nrules: []\n')
            inventory=put('prices.csv',f'ticker,path,sha256,source_tickers,segment_count,lifecycle_rule_id,rows_before_selection,data_start,data_end\nA,{price["path"]},{price["sha256"]},A,1,,4,2020-01-01,2020-01-06\n')
            sidecar=put('sidecar.json',{'content_sha256':price['sha256'], 'dataset_key':'A',
                'price_basis':'unadjusted_nominal_trade_price', 'whole_lot_execution_use_only':True,
                'return_usage_allowed':False})
            execution_inventory=put('execution.csv',f'ticker,status,path,sha256,sidecar_path,sidecar_sha256\nA,FETCHED,{price["path"]},{price["sha256"]},{sidecar["path"]},{sidecar["sha256"]}\n')
            execution=put('execution.json',{'whole_lot_execution_use_only':True,'status':'READY',
                                           'artifacts':{'inventory':execution_inventory}})
            discovery=put('discovery.json',{'artifacts':{'eligible_securities':member}})
            put('run/manifest.json',{'inputs':{'discovery_manifest':discovery},'run_contract':{'fit_days':1}})
            child=put('run/jobs/strict_technology/2020-01-07/k1/shard0000/manifest.json',dict(
                promotion_allowed=False,research_track='portfolio_optimization',selection_date='2020-01-07',
                universe_track='strict_technology',holding_count=1,candidate_security_count=1,candidate_issuer_count=1,
                training_return_rows=3,training_end='2020-01-06',incumbent_weights={'A':1.},excluded_for_history=[],
                inputs=dict(membership_audit=membership,identity_audit=identity,security_lifecycle=lifecycle,
                            target_nav=nav,execution_price_manifest=execution),artifacts={'price_inventory':inventory}))
            contract=fixture()[1]['contract']; contract.update(fit_days=1,window_days=1,step_days=1)
            value=prepare_joint_weight_history_inputs(child['path'],child['sha256'],evaluation_contract=contract,
                    training_lookback_days=3,minimum_price_rows_before_selection=1)
            self.assertEqual(value['universe'].ticker.tolist(),['A'])
            self.assertEqual(value['returns'].index.tolist(),list(pd.to_datetime(['2020-01-02','2020-01-03','2020-01-06'])))
            self.assertEqual(value['incumbent_weights'],{'A':1.})
            self.assertFalse(value['provenance']['revised_return_data_used'])
            self.assertFalse(value['provenance']['external_root_authentication'])


if __name__ == '__main__':
    unittest.main()
