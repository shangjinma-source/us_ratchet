"""Synthetic six-decision control inputs call both real control APIs."""
from copy import deepcopy
from unittest import TestCase, main
import pandas as pd
from backtest import ndx_multidecision_incumbent_inputs_research as inputs
from backtest.ndx_incumbent_flow_split_control_research import simulate_incumbent_flow_split_control
from test_ndx_multidecision_incumbent_inputs_research import fixture, ref


class EngineIntegrationTests(TestCase):
    def test_six_decisions_keep_track_and_lane_cash_independent(self):
        arguments = fixture()
        original = arguments['original_eight_evidence']['document']
        for row in original['rows']:
            for quote in row['channel']['quote_rows']:
                quote['nominal_open_exact'] = quote['nominal_close_exact'] = '100'
            row['channel']['quote_rows_sha256'] = inputs.digest(row['channel']['quote_rows'])
        candidate = arguments['candidate_evidence']['document']['inputs']
        flow = dict(session='2026-04-02', amount_usd=1000., currency='USD',
                    timing='BEFORE_OPEN', source_reference=ref('integration-flow'))
        for track in candidate['rows'][4]['tracks']:
            track['stateful_input']['external_flows'] = [deepcopy(flow)]
        candidate['content_sha256'] = inputs.digest({k:v for k,v in candidate.items() if k != 'content_sha256'})
        prepared = inputs.prepare_incumbent_account_inputs(**arguments)
        original_digest = inputs.digest(prepared)
        for lane_index in (4, 5):
            for track in prepared['rows'][lane_index]['tracks']:
                kwargs = deepcopy(track['engine_binding']['keyword_arguments'])
                for field in ('closes', 'opens'):
                    matrix = kwargs[field]
                    kwargs[field] = pd.DataFrame(matrix['data'], columns=matrix['columns'], index=pd.to_datetime(matrix['index']))
                result = simulate_incumbent_flow_split_control(**kwargs)
                injected = 1000. if lane_index == 4 else 0.
                self.assertEqual(result['summary']['total_cash_injection_usd'], injected)
                self.assertEqual(len(result['daily']), len(kwargs['closes']))
                self.assertEqual(result['daily'][0]['normalized_twr'], 1.)
                fees = (sum(row['fees_usd'] for row in result['daily']) if track['track'] == 'CONTINUOUS'
                        else sum(row['transaction_cost_usd'] for row in result['trades']))
                last = result['daily'][-1]
                equity = last['close_equity_usd'] if track['track'] == 'CONTINUOUS' else last['total_value_usd']
                self.assertAlmostEqual(equity, 25000. + injected - fees, places=7)
        self.assertEqual(inputs.digest(prepared), original_digest)


if __name__ == '__main__':
    main()
