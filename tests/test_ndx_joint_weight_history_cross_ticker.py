"""Independent end-to-end lifecycle input test, not a helper-only stitch test."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from backtest.ndx_joint_weight_history_inputs import prepare_joint_weight_history_inputs
from backtest.ndx_joint_weight_history_inputs import _boolean_mask, _positive_integer, _validate_nominal_sidecar
import pandas as pd
from test_ndx_joint_weight_evaluation import fixture


class HistoryCrossTickerTests(unittest.TestCase):
    def test_nominal_semantics_and_typed_metadata_fail_closed(self):
        sidecar = dict(content_sha256='a'*64, dataset_key='NEW',
                       price_basis='unadjusted_nominal_trade_price',
                       whole_lot_execution_use_only=True, return_usage_allowed=False)
        _validate_nominal_sidecar(sidecar, 'NEW', 'a'*64)
        for key, value in [('dataset_key', 'OTHER'), ('price_basis', 'adjusted_close'),
                           ('whole_lot_execution_use_only', 1), ('return_usage_allowed', 0)]:
            changed = dict(sidecar); changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                _validate_nominal_sidecar(changed, 'NEW', 'a'*64)
        for value in (True, 1.5, '1'):
            with self.assertRaises(ValueError):
                _positive_integer(value, 'count')
        for values in ([1, 0], ['True', 'False']):
            with self.assertRaises(ValueError):
                _boolean_mask(pd.Series(values), 'test')

    def test_complete_child_crosses_ticker_era_without_losing_nominal_or_return_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def put(name, value):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                raw = value.encode() if isinstance(value, str) else json.dumps(value).encode()
                path.write_bytes(raw)
                return dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest())
            old = put('OLD.csv', 'Date,Close,Volume\n2020-01-01,10,100\n2020-01-02,11,100\n')
            new = put('NEW.csv', 'Date,Close,Volume\n2020-01-03,12,100\n2020-01-06,13,100\n')
            nav = put('nav.csv', 'Date,Close\n2020-01-01,1\n2020-01-02,1.1\n2020-01-03,1.2\n2020-01-06,1.3\n')
            members = put('members.csv', 'selection_date,universe_track,membership_window_eligible,ticker,security_id,issuer_id,risk_chain\n2020-01-07,strict_technology,True,NEW,security:0000000002:ABC123456,issuer:0000000002,software\n')
            membership = put('membership.csv', 'selection_date,universe_track,security_id,input_ready\n2020-01-07,strict_technology,security:0000000002:ABC123456,True\n')
            identity = put('identity.csv', 'identity_status,issuer_ids\nIDENTITY_MATCH,issuer:0000000002\n')
            lifecycle = put('lifecycle.yaml', '''schema_version: 1
rules:
  - rule_id: era
    cik: '0000000002'
    cusip: ABC123456
    recognized_tickers: [OLD, NEW]
    intervals:
      - {effective_from: null, effective_to: '2020-01-02', price_ticker: OLD}
      - {effective_from: '2020-01-03', effective_to: null, price_ticker: NEW}
''')
            prices = put('prices.csv', 'ticker,path,sha256,source_tickers,segment_count,lifecycle_rule_id,rows_before_selection,data_start,data_end\n'
                         f'NEW,{old["path"]};{new["path"]},{old["sha256"]};{new["sha256"]},OLD;NEW,2,era,4,2020-01-01,2020-01-06\n')
            execution_rows = []
            for ticker, price in [('OLD', old), ('NEW', new)]:
                sidecar = put(ticker+'.json', {'content_sha256': price['sha256'], 'dataset_key':ticker,
                    'price_basis':'unadjusted_nominal_trade_price', 'whole_lot_execution_use_only':True,
                    'return_usage_allowed':False})
                execution_rows.append(f'{ticker},FETCHED,{price["path"]},{price["sha256"]},{sidecar["path"]},{sidecar["sha256"]}\n')
            execution_inventory = put('execution.csv', 'ticker,status,path,sha256,sidecar_path,sidecar_sha256\n'+''.join(execution_rows))
            execution = put('execution.json', dict(whole_lot_execution_use_only=True,status='READY',
                                                   artifacts={'inventory': execution_inventory}))
            discovery = put('discovery.json', {'artifacts': {'eligible_securities': members}})
            put('run/manifest.json', {'inputs': {'discovery_manifest': discovery}})
            child = put('run/jobs/strict_technology/2020-01-07/k1/shard0000/manifest.json', dict(
                promotion_allowed=False, research_track='portfolio_optimization', selection_date='2020-01-07',
                universe_track='strict_technology', holding_count=1, candidate_security_count=1,
                candidate_issuer_count=1, training_return_rows=3, training_end='2020-01-06',
                incumbent_weights={'NEW':1.}, excluded_for_history=[],
                inputs=dict(membership_audit=membership, identity_audit=identity, security_lifecycle=lifecycle,
                            target_nav=nav, execution_price_manifest=execution), artifacts={'price_inventory':prices}))
            contract = fixture()[1]['contract']
            contract.update(fit_days=1, window_days=1, step_days=1)
            value = prepare_joint_weight_history_inputs(child['path'], child['sha256'],
                evaluation_contract=contract, training_lookback_days=3, minimum_price_rows_before_selection=1)
            self.assertEqual(value['nominal_prices']['NEW'].tolist(), [11.,12.,13.])
            self.assertEqual(value['returns']['NEW'].tolist(), [11/10-1,12/11-1,13/12-1])
            self.assertEqual(value['universe'].security_id.tolist(), ['security:0000000002:ABC123456'])
            self.assertFalse(value['provenance']['revised_return_data_used'])
            # Re-signing the input inventory cannot make a missing old era legal.
            changed = put('prices.csv', 'ticker,path,sha256,source_tickers,segment_count,lifecycle_rule_id,rows_before_selection,data_start,data_end\n'
                          f'NEW,{new["path"]},{new["sha256"]},NEW,1,era,4,2020-01-01,2020-01-06\n')
            payload = json.loads(Path(child['path']).read_text())
            payload['artifacts']['price_inventory'] = changed
            replacement = put('run/jobs/strict_technology/2020-01-07/k1/shard0000/manifest.json', payload)
            with self.assertRaisesRegex(ValueError, 'segments missing'):
                prepare_joint_weight_history_inputs(replacement['path'], replacement['sha256'],
                    evaluation_contract=contract, training_lookback_days=3, minimum_price_rows_before_selection=1)


if __name__ == '__main__':
    unittest.main()
