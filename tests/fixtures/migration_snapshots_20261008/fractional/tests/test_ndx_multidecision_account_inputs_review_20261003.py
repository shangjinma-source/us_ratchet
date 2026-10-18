"""Independent input/engine compatibility and preserved-domain checks."""
from copy import deepcopy
import unittest
import pandas as pd
from backtest import ndx_multidecision_account_inputs_research as core
from backtest import ndx_dynamic_fractional_flow_split_research_v2 as engine
from test_ndx_multidecision_account_inputs_research import fixture, ref, reuse


class Review(unittest.TestCase):
    def test_ready_binding_runs_exact_frozen_signature_and_owns_state(self):
        a = fixture(); reuse(a)
        a['execution_contract']['cash_flow_role'] = 'EXPLICIT_NEW_CASH_RESEARCH'
        key = core.MODES[1] + '|RETURN'
        a['flows_by_lane'][key] = [dict(session='2026-04-02', amount_usd=1000., currency='USD',
            timing='BEFORE_OPEN', source_reference=ref('ind-flow'))]
        saved = core.prepare_multidecision_account_inputs(**a)
        track = saved['rows'][4]['tracks'][0]
        self.assertEqual(track['status'], 'ENGINE_INPUTS_PREPARED_NOT_EXECUTED')
        kw = deepcopy(track['engine_binding']['keyword_arguments'])
        for name in ('opens', 'closes'):
            f = kw[name]; kw[name] = pd.DataFrame(f['data'], columns=f['columns'], index=pd.to_datetime(f['index']))
        result = engine.simulate_dynamic_fractional_flow_split_research(**kw)
        self.assertEqual(result['summary']['rebalance_count'], 6)
        self.assertEqual(result['summary']['total_cash_injection_usd'], 1000.)
        self.assertIsNone(result['daily'][2]['execution_status'])
        self.assertEqual(saved['rows'][4]['tracks'][1]['status'], 'ENGINE_INPUTS_PREPARED_NOT_EXECUTED')
        whole_binding = saved['rows'][4]['tracks'][1]['engine_binding']
        self.assertEqual(whole_binding['source_reference']['sha256'], '35c19184f08a0394838171fa61afeb781cd4f314799058063186d9c3d38376a8')
        self.assertEqual(whole_binding['keyword_arguments']['external_flows'], a['flows_by_lane'][key])
        # Reused fitted targets cannot alias account state or flow inventories.
        track['stateful_input']['external_flows'][0]['amount_usd'] = 99.
        self.assertEqual(saved['rows'][5]['tracks'][0]['stateful_input']['external_flows'], [])
        self.assertEqual(track['engine_binding']['keyword_arguments']['external_flows'][0]['amount_usd'], 1000.)
        self.assertEqual(len(saved['outer_coordinate_rows_preserved']), 48)
        self.assertEqual(len(saved['rows']), 8)
        for e in (core.FRACTIONAL_ENGINE, core.WHOLE_ENGINE):
            self.assertEqual(saved['source_hashes'][e['path']], e['sha256'])

    def test_ready_cannot_contain_flow_type_or_positive_price_underflow(self):
        a = fixture(); a['execution_contract']['cash_flow_role'] = 'EXPLICIT_NEW_CASH_RESEARCH'
        a['flows_by_lane'][core.MODES[1] + '|RETURN'] = [dict(session='2026-04-02', amount_usd='1000',
            currency='USD', timing='BEFORE_OPEN', source_reference=ref('string-flow'))]
        with self.assertRaises(ValueError): core.prepare_multidecision_account_inputs(**a)
        a = fixture(); a['execution_contract']['cash_flow_role'] = 'EXPLICIT_NEW_CASH_RESEARCH'
        e = dict(session='2026-04-02', amount_usd=100., currency='USD', timing='BEFORE_OPEN', source_reference=ref('same-receipt'))
        a['flows_by_lane'][core.MODES[1] + '|RETURN'] = [e, {**e, 'amount_usd': 101.}]
        with self.assertRaises(ValueError): core.prepare_multidecision_account_inputs(**a)
        a = fixture(); ch = a['price_evidence']['document']['rows'][0]['channel']
        row = next(x for x in ch['quote_rows'] if x['session'] == '2026-04-02')
        row['nominal_open_exact'] = '1/1' + '0' * 400
        ch['quote_rows_sha256'] = core.digest(ch['quote_rows'])
        a['price_evidence']['readback']['per_channel'][0]['quote_rows_sha256'] = ch['quote_rows_sha256']
        with self.assertRaises(ValueError): core.prepare_multidecision_account_inputs(**a)

    def test_complete_issuer_domain_and_missing_cell_not_cash(self):
        a = fixture()
        # Destroy the original two-class issuer relation outside selected four.
        a['price_evidence']['document']['rows'][-1]['coordinate']['issuer_id'] = 'EXTRA_77TH_ISSUER'
        with self.assertRaises(ValueError): core.prepare_multidecision_account_inputs(**a)
        a = fixture(); ch = a['price_evidence']['document']['rows'][0]['channel']
        row = next(x for x in ch['quote_rows'] if x['session'] == '2026-04-02')
        row['nominal_close_exact'] = None
        ch['quote_rows_sha256'] = core.digest(ch['quote_rows'])
        a['price_evidence']['readback']['per_channel'][0]['quote_rows_sha256'] = ch['quote_rows_sha256']
        out = core.prepare_multidecision_account_inputs(**a)
        for track in out['rows'][4]['tracks']:
            self.assertEqual(track['status'], 'BLOCKED_ENGINE_OR_SOURCE_INPUT')
            f = track['stateful_input']['closes']
            self.assertIsNone(f['data'][f['index'].index('2026-04-02')][0])
            self.assertEqual(len(track['stateful_input']['schedule']), 6)
        a = fixture()
        a['price_evidence']['document']['rows'][0]['channel']['event_policies'] = [dict(
            session='2026-03-31', kind='ORDINARY_SPLIT', numerator=2, denominator=1)]
        track = core.prepare_multidecision_account_inputs(**a)['rows'][4]['tracks'][0]
        self.assertEqual(track['status'], 'BLOCKED_ENGINE_OR_SOURCE_INPUT')


if __name__ == '__main__': unittest.main()
