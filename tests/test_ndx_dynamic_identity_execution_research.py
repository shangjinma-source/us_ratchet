from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from backtest import ndx_dynamic_identity_execution_research as wrapper


class IdentityExecutionTests(unittest.TestCase):
    def fixture(self, directory, rename_index=None):
        days = ['2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05', '2024-01-08']
        identity = dict(security_id='SEC1', issuer_id='ISSUER1', cik='0000000001', cusip='000000001')

        def save(name, payload):
            path = Path(directory) / name; raw = json.dumps(payload).encode(); path.write_bytes(raw)
            return dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest())

        partitions = [('A', days)] if rename_index is None else [('A', days[:rename_index]), ('X', days[rename_index:])]
        intervals = []
        for ticker, subset in partitions:
            evidence = dict(identity, schema='ndx_price_identity_evidence_v1', observed_ticker=ticker,
                provider_instrument_id='INST1', first_session=subset[0], last_session=subset[-1],
                evidence_available_session=days[0])
            artifact = dict(identity, schema='ndx_identity_price_artifact_v1', observed_ticker=ticker,
                provider_instrument_id='INST1', open_column='Open', close_column='Close', currency='USD',
                price_basis='UNADJUSTED', rows=[dict(session=day, Open=10., Close=10.) for day in subset])
            intervals.append(dict(first_session=subset[0], last_session=subset[-1], observed_ticker=ticker,
                open_column='Open', close_column='Close', provider_instrument_id='INST1',
                identity_evidence=save(ticker+'identity.json', evidence),
                price_artifact=save(ticker+'prices.json', artifact)))
        events = []
        if rename_index is not None:
            evidence = dict(identity, schema='ndx_same_security_rename_evidence_v1', event_id='RENAME',
                event_type='SAME_SECURITY_SYMBOL_CHANGE', effective_session=days[rename_index], from_ticker='A',
                to_ticker='X', evidence_available_session=days[0])
            events.append(dict(event_id='RENAME', effective_session=days[rename_index], from_ticker='A',
                               to_ticker='X', evidence=save('rename.json', evidence)))
        securities = {'SEC1': dict(issuer_id='ISSUER1', cik='0000000001', cusip='000000001',
                                  intervals=intervals, rename_events=events)}
        schedule = []
        for index in (0, 3):
            ticker = 'A' if rename_index is None or index < rename_index else 'X'
            schedule.append(dict(decision_date=days[index], execution_date=days[index+1],
                targets={'SEC1': dict(ticker=ticker, issuer_id='ISSUER1', target_weight=1.)}))
        return dict(calendar=days, securities=securities, schedule=schedule,
            risk_chains_by_decision={row['decision_date']: {'SEC1': 'CHAIN1'} for row in schedule},
            corporate_actions=[], initial_cash_usd=1000., minimum_cash_buffer_usd=100.,
            valuation_end_date=days[-1], transaction_cost_bps=10., max_single_weight=1.,
            min_single_weight=0., top_weight_cap=1., minimum_effective_n_ratio=0., risk_chain_top1_cap=1.)

    def test_rename_between_decision_and_open_uses_real_labels_frozen_lots(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.fixture(directory, 1); original = deepcopy(args)
            result = wrapper.simulate_dynamic_identity_execution_research(**args)
            self.assertEqual(result['decisions'][0]['targets']['SEC1']['ticker'], 'A')
            self.assertEqual(result['trades'][0]['ticker'], 'X')
            self.assertEqual(result['executions'][0]['desired_shares'], result['decisions'][0]['desired_shares'])
            self.assertEqual(result['trades'][0]['share_delta'], result['decisions'][0]['delta']['SEC1'])
            self.assertEqual(len(result['identity_events']), 1)
            self.assertEqual(args, original)
            self.assertFalse(result['promotion_allowed'])

    def test_between_decisions_rename_preserves_shares_cash_and_fees(self):
        with tempfile.TemporaryDirectory() as directory:
            result = wrapper.simulate_dynamic_identity_execution_research(**self.fixture(directory, 2))
            before, after = result['daily'][1:3]
            self.assertEqual(before['tickers']['SEC1'], 'A')
            self.assertEqual(after['tickers']['SEC1'], 'X')
            self.assertEqual(before['shares'], after['shares'])
            self.assertEqual(before['cash_usd'], after['cash_usd'])
            self.assertFalse(any(row['session'] == after['session'] for row in result['trades']))

    def test_next_open_gap_rejects_without_resizing_frozen_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.fixture(directory, 1)
            normal = wrapper.simulate_dynamic_identity_execution_research(**args)
            reference = args['securities']['SEC1']['intervals'][1]['price_artifact']
            path = Path(reference['path']); content = json.loads(path.read_text())
            content['rows'][0]['Open'] = 1000.
            raw = json.dumps(content).encode(); path.write_bytes(raw)
            reference['sha256'] = hashlib.sha256(raw).hexdigest()
            changed = wrapper.simulate_dynamic_identity_execution_research(**args)
            self.assertEqual(normal['decisions'][0], changed['decisions'][0])
            self.assertEqual(changed['executions'][0]['status'], 'REJECTED')
            self.assertIn('CASH_BUFFER', changed['executions'][0]['failure_reasons'])
            self.assertEqual(changed['executions'][0]['desired_shares'], normal['decisions'][0]['desired_shares'])

    def test_no_rename_matches_original_economic_fields_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.fixture(directory)
            prices = pd.DataFrame({'A': [10.]*5}, index=pd.DatetimeIndex(args['calendar']))
            direct = {key: value for key, value in args.items() if key not in ('calendar', 'securities')}
            expected = wrapper.engine.simulate_dynamic_frozen_execution_research(closes=prices, opens=prices, **direct)
            actual = wrapper.simulate_dynamic_identity_execution_research(**args)
            self.assertEqual(actual['summary'], expected['summary'])
            for group in ('daily', 'decisions', 'executions', 'trades'):
                for old, new in zip(expected[group], actual[group]):
                    for key, value in old.items():
                        if key == 'targets':
                            self.assertEqual({sid: {k:v for k,v in target.items() if k != 'internal_price_column'}
                                              for sid,target in new[key].items()}, value)
                        else: self.assertEqual(new[key], value, (group, key))

    def test_bad_target_and_unverified_override_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for fault in ('ticker', 'issuer', 'sid', 'override'):
                args = self.fixture(directory)
                target = args['schedule'][0]['targets']['SEC1']
                if fault == 'ticker': target['ticker'] = 'X'
                if fault == 'issuer': target['issuer_id'] = 'OTHER'
                if fault == 'sid': args['schedule'][0]['targets'] = {'UNKNOWN': target}
                if fault == 'override': args['identity_events'] = []
                with self.assertRaises(ValueError): wrapper.simulate_dynamic_identity_execution_research(**args)

    def test_split_cancels_pending_rename_does_not(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.fixture(directory, 1)
            args['corporate_actions'] = [dict(security_id='SEC1', session=args['calendar'][1],
                new_shares=2, old_shares=1, source_url='https://example.org/synthetic', evidence_sha256='a'*64)]
            result = wrapper.simulate_dynamic_identity_execution_research(**args)
            self.assertEqual(result['executions'][0]['status'], 'CANCELLED_SPLIT')
            self.assertEqual(result['executions'][0]['plan']['targets']['SEC1']['ticker'], 'A')
            event = result['corporate_actions'][0]['applied_events'][0]['event']
            self.assertEqual(event['security_id'], 'SEC1')
            self.assertEqual(event['ticker'], 'X')
            self.assertEqual(len(result['identity_events']), 1)

    def test_source_changes_during_execution_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.fixture(directory)
            original = wrapper.engine.simulate_dynamic_frozen_execution_research

            def change_source(**kwargs):
                result = original(**kwargs)
                path = args['securities']['SEC1']['intervals'][0]['price_artifact']['path']
                Path(path).write_text('{}')
                return result

            with patch.object(wrapper.engine, 'simulate_dynamic_frozen_execution_research', side_effect=change_source):
                with self.assertRaisesRegex(ValueError, 'source drift'):
                    wrapper.simulate_dynamic_identity_execution_research(**args)


if __name__ == '__main__': unittest.main()
