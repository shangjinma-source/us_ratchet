"""Independent synthetic accounting oracles; these do not authenticate real data."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from backtest import ndx_dynamic_identity_execution_research as wrapper


class IndependentIdentityOracles(unittest.TestCase):
    def fixture(self, directory, rename=False, split=False):
        days = ['2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05', '2024-01-08', '2024-01-09']
        securities = {}
        frames = {}
        for sid, ticker, issuer, cik, cusip, price in (
                ('S1', 'AAA', 'I1', '0000000001', '000000001', 10.),
                ('S2', 'BBB', 'I2', '0000000002', '000000002', 20.),
                ('S3', 'AAC', 'I1', '0000000001', '000000003', 15.)):
            identity = dict(security_id=sid, issuer_id=issuer, cik=cik, cusip=cusip)

            def save(name, payload):
                path = Path(directory) / (sid + name + '.json')
                raw = json.dumps(payload).encode()
                path.write_bytes(raw)
                return dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest())

            partitions = [(ticker, days)]
            if sid == 'S1' and rename:
                partitions = [(ticker, days[:2]), ('AXX', days[2:])]
            intervals = []
            frames[ticker] = [price / 2 if split and sid == 'S1' and day >= days[2] else price for day in days]
            for label, subset in partitions:
                evidence = dict(identity, schema='ndx_price_identity_evidence_v1', observed_ticker=label,
                    provider_instrument_id=sid, first_session=subset[0], last_session=subset[-1],
                    evidence_available_session=days[0])
                artifact = dict(identity, schema='ndx_identity_price_artifact_v1', observed_ticker=label,
                    provider_instrument_id=sid, open_column='Open', close_column='Close', currency='USD',
                    price_basis='UNADJUSTED', rows=[dict(session=day, Open=frames[ticker][days.index(day)],
                    Close=frames[ticker][days.index(day)]) for day in subset])
                intervals.append(dict(first_session=subset[0], last_session=subset[-1], observed_ticker=label,
                    provider_instrument_id=sid, open_column='Open', close_column='Close',
                    identity_evidence=save(label+'identity', evidence), price_artifact=save(label+'prices', artifact)))
            events = []
            if sid == 'S1' and rename:
                evidence = dict(identity, schema='ndx_same_security_rename_evidence_v1', event_id='R1',
                    event_type='SAME_SECURITY_SYMBOL_CHANGE', effective_session=days[2],
                    from_ticker=ticker, to_ticker='AXX', evidence_available_session=days[0])
                events = [dict(event_id='R1', effective_session=days[2], from_ticker=ticker,
                    to_ticker='AXX', evidence=save('rename', evidence))]
            securities[sid] = dict(issuer_id=issuer, cik=cik, cusip=cusip, intervals=intervals, rename_events=events)
        baskets = [dict(S1=('AAA', 'I1', 1.)), dict(S1=('AXX' if rename else 'AAA', 'I1', .5),
            S2=('BBB', 'I2', .5)), dict(S3=('AAC', 'I1', 1.))]
        schedule = [dict(decision_date=days[index], execution_date=days[index+1],
            targets={sid: dict(ticker=label, issuer_id=issuer, target_weight=weight)
                for sid, (label, issuer, weight) in basket.items()}) for index, basket in zip((0, 2, 4), baskets)]
        actions = [dict(security_id='S1', session=days[2], new_shares=2, old_shares=1,
            source_url='https://example.org/synthetic-split', evidence_sha256='a'*64)] if split else []
        args = dict(calendar=days, securities=securities, schedule=schedule,
            risk_chains_by_decision={row['decision_date']: {sid: sid for sid in row['targets']} for row in schedule},
            corporate_actions=actions, initial_cash_usd=1000., minimum_cash_buffer_usd=100.,
            valuation_end_date=days[-1], transaction_cost_bps=10., max_single_weight=1.,
            min_single_weight=0., top_weight_cap=1., minimum_effective_n_ratio=0., risk_chain_top1_cap=1.)
        return args, pd.DataFrame(frames, index=pd.DatetimeIndex(days))

    def assert_economics(self, actual, expected):
        self.assertEqual(actual['summary'], expected['summary'])
        for group in ('daily', 'decisions', 'executions', 'trades'):
            self.assertEqual(len(actual[group]), len(expected[group]))
            for new, old in zip(actual[group], expected[group]):
                for key, value in old.items():
                    if key == 'targets':
                        self.assertEqual({sid: {k: v for k, v in target.items() if k != 'internal_price_column'}
                            for sid, target in new[key].items()}, value)
                    else:
                        self.assertEqual(new[key], value, (group, key))

    def test_multisid_variable_k_and_share_class_rotation_exact_economics(self):
        with tempfile.TemporaryDirectory() as directory:
            args, prices = self.fixture(directory)
            direct = {key: value for key, value in args.items() if key not in ('calendar', 'securities')}
            expected = wrapper.engine.simulate_dynamic_frozen_execution_research(closes=prices, opens=prices, **direct)
            actual = wrapper.simulate_dynamic_identity_execution_research(**args)
            self.assert_economics(actual, expected)
            self.assertEqual(actual['summary']['k_path'], [1, 2, 1])
            final = actual['executions'][-1]
            self.assertEqual(final['status'], 'FILLED')
            self.assertEqual(set(final['shares_after']), {'S3'})
            trades = [trade for trade in actual['trades'] if trade['session'] == final['session']]
            self.assertEqual({trade['security_id'] for trade in trades}, {'S1', 'S2', 'S3'})
            fees = sum(abs(trade['share_delta']) * trade['price_usd'] * .001 for trade in trades)
            self.assertAlmostEqual(final['projected_fees_usd'], fees)
            self.assertTrue(all(trade['transaction_cost_usd'] > 0 for trade in trades))
            self.assertEqual([(trade['security_id'], trade['share_delta'] > 0) for trade in trades],
                [('S1', False), ('S2', False), ('S3', True)])

    def test_held_split_and_rename_same_day_preserve_equity_no_phantom_fees(self):
        with tempfile.TemporaryDirectory() as directory:
            args, _ = self.fixture(directory, rename=True, split=True)
            actual = wrapper.simulate_dynamic_identity_execution_research(**args)
            before, after = actual['daily'][1:3]
            self.assertGreater(before['shares']['S1'], 0)
            self.assertEqual(after['shares']['S1'], 2 * before['shares']['S1'])
            self.assertEqual(after['cash_usd'], before['cash_usd'])
            self.assertEqual(after['total_value_usd'], before['total_value_usd'])
            self.assertEqual(after['tickers']['S1'], 'AXX')
            self.assertFalse(any(trade['session'] == after['session'] for trade in actual['trades']))
            action = actual['corporate_actions'][0]
            self.assertIsNone(action['cancelled_plan'])
            self.assertEqual(action['split_fees_usd'], 0.)
            self.assertEqual(action['applied_events'][0]['event']['ticker'], 'AXX')
            self.assertEqual(actual['executions'][1]['status'], 'FILLED')

    def test_rehashed_wrong_real_binding_rejected_internally(self):
        with tempfile.TemporaryDirectory() as directory:
            args, _ = self.fixture(directory)
            reference = args['securities']['S1']['intervals'][0]['price_artifact']
            path = Path(reference['path'])
            payload = json.loads(path.read_text())
            payload['cusip'] = '000000003'
            raw = json.dumps(payload).encode()
            path.write_bytes(raw)
            reference['sha256'] = hashlib.sha256(raw).hexdigest()
            with self.assertRaisesRegex(ValueError, 'Price artifact identity'):
                wrapper.simulate_dynamic_identity_execution_research(**args)

    def test_held_split_cancels_existing_pending_basket_without_relabelling_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            args, _ = self.fixture(directory, rename=True, split=True)
            second = deepcopy(args['schedule'][0])
            second.update(decision_date=args['calendar'][1], execution_date=args['calendar'][2])
            args['schedule'].insert(1, second)
            args['risk_chains_by_decision'][second['decision_date']] = {'S1': 'S1'}
            actual = wrapper.simulate_dynamic_identity_execution_research(**args)
            cancelled = actual['executions'][1]
            self.assertEqual(cancelled['status'], 'CANCELLED_SPLIT')
            self.assertEqual(cancelled['plan']['targets']['S1']['ticker'], 'AAA')
            action = actual['corporate_actions'][0]
            self.assertEqual(action['cancelled_plan']['targets']['S1']['ticker'], 'AAA')
            self.assertGreater(action['applied_events'][0]['pre_shares'], 0)
            self.assertEqual(action['applied_events'][0]['event']['ticker'], 'AXX')
            self.assertEqual(actual['daily'][2]['shares']['S1'], actual['daily'][1]['shares']['S1'] * 2)
            self.assertFalse(any(trade['session'] == args['calendar'][2] for trade in actual['trades']))

    def test_fractional_reverse_split_with_rename_still_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            args, _ = self.fixture(directory, rename=True, split=True)
            args['corporate_actions'][0].update(new_shares=1, old_shares=100)
            with self.assertRaisesRegex(ValueError, 'UNRESOLVED_FRACTIONAL_SPLIT_ENTITLEMENT'):
                wrapper.simulate_dynamic_identity_execution_research(**args)

    def test_caller_bridge_injection_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            args, _ = self.fixture(directory)
            for key in ('closes', 'opens', 'identity_events', 'bridge', 'price_bridge'):
                changed = deepcopy(args)
                changed[key] = {}
                with self.assertRaisesRegex(ValueError, 'override forbidden'):
                    wrapper.simulate_dynamic_identity_execution_research(**changed)


if __name__ == '__main__':
    unittest.main()
