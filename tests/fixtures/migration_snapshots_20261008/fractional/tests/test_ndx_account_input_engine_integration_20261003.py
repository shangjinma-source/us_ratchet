"""Synthetic input-to-engine integration; never consumes actual research results."""
from copy import deepcopy
import unittest
import pandas as pd
import test_ndx_multidecision_account_inputs_research as fixture_module
from backtest import ndx_dynamic_fractional_flow_split_research_v2 as engine


class EngineBindingIntegration(unittest.TestCase):
    def test_six_decisions_flow_and_split_bind_to_real_fractional_api(self):
        args = fixture_module.fixture()
        source = args['price_evidence']
        for index, row in enumerate(source['document']['rows']):
            channel = row['channel']
            for quote in channel['quote_rows']:
                price = '50' if index == 0 and quote['session'] >= '2026-04-06' else '100'
                quote['nominal_open_exact'] = quote['nominal_close_exact'] = price
            if index == 0:
                channel['event_policies'] = [dict(session='2026-04-06',kind='ORDINARY_SPLIT',numerator=2,denominator=1)]
            channel['quote_rows_sha256'] = fixture_module.m.digest(channel['quote_rows'])
            source['readback']['per_channel'][index]['quote_rows_sha256'] = channel['quote_rows_sha256']
        args['execution_contract']['cash_flow_role'] = 'EXPLICIT_NEW_CASH_RESEARCH'
        key = fixture_module.m.MODES[1]+'|RETURN'
        args['flows_by_lane'][key] = [dict(session='2026-04-02',amount_usd=1000.,currency='USD',
            timing='BEFORE_OPEN',source_reference=fixture_module.ref('one-lane-deposit'))]
        prepared = fixture_module.m.prepare_multidecision_account_inputs(**args)
        saved_digest = fixture_module.m.digest(prepared)
        results = []
        for lane_index in (4,5):
            track = prepared['rows'][lane_index]['tracks'][0]
            self.assertEqual(track['status'],'ENGINE_INPUTS_PREPARED_NOT_EXECUTED')
            binding = track['engine_binding']
            self.assertEqual(binding['function'],'simulate_dynamic_fractional_flow_split_research')
            keywords = deepcopy(binding['keyword_arguments'])
            for field in binding['dataframe_restoration_required']:
                value = keywords[field]
                keywords[field] = pd.DataFrame(value['data'],index=pd.to_datetime(value['index']),columns=value['columns'])
            result = engine.simulate_dynamic_fractional_flow_split_research(**keywords)
            self.assertEqual(result['summary']['rebalance_count'],6)
            self.assertEqual(result['summary']['split_event_count'],1)
            self.assertEqual(result['calendar'],track['stateful_input']['calendar'])
            injected = 1000. if lane_index == 4 else 0.
            summary = result['summary']
            self.assertEqual(summary['total_cash_injection_usd'],injected)
            self.assertAlmostEqual(summary['terminal_equity_usd'],25000.+injected-summary['total_fees_usd'],places=7)
            self.assertLess(summary['chained_twr'],0.)
            results.append(result)
        self.assertEqual(fixture_module.m.digest(prepared),saved_digest)
        self.assertEqual(results[1]['summary']['flow_event_count'],0)
        self.assertEqual(results[0]['summary']['flow_event_count'],1)


if __name__ == '__main__': unittest.main()
