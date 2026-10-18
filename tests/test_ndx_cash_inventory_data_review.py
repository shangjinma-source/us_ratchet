"""Independent synthetic/temp-only inventory checks; no saved build."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_ndx_conditional_new_cash_inventory_20260925 import module as m, fixture


class IndependentInventoryTests(unittest.TestCase):
    def test_same_ticker_different_sid_not_borrowed_from_other_lane(self):
        docs, refs = fixture()
        docs['RETURN_identity']['rows'][0]['security_id'] = 'OTHER_CLASS'
        result = m.assemble(docs, refs)
        row = next(r for r in result['rows'][0]['securities'] if r['security_id'] == 'A')
        borrowed = [p for p in row['execution_open_observations'] if p['reference']['path'] == refs['RETURN_price']['path']]
        self.assertEqual(borrowed, [], 'Another lane identity cannot bind this ticker matrix')
        self.assertIn('AMBIGUOUS_OR_MISSING_LOCAL_MATRIX_SECURITY_BINDING', row['gaps'])

    def test_old_holding_survives_target_exit_and_close_cannot_fill_open(self):
        docs, refs = fixture()
        for key in ('benchmark', 'control'):
            daily = docs[key]['incumbent']['daily'] if key == 'benchmark' else docs[key]['execution']['daily']
            daily[0]['shares']['EXITED'] = 7
            daily[0]['tickers']['EXITED'] = 'OLD'
        day = m.CLOCK[0][1]
        del docs['RETURN_price']['matrices']['open'][day]['AAA']
        docs['control']['nominal_quotes']['by_ticker']['AAA']['rows'] = []
        r = m.assemble(docs, refs)['rows'][0]
        self.assertIn('EXITED', r['union_security_ids'])
        a = next(s for s in r['securities'] if s['security_id'] == 'A')
        self.assertEqual(a['execution_open_observations'], [])
        self.assertIn('EXECUTION_OPEN_MISSING', a['gaps'])

    def test_all_coordinates_controls_overlay_and_no_authority(self):
        docs, refs = fixture(); r = m.assemble(docs, refs)
        self.assertEqual(len({(x['lane'], x['decision_date'], x['execution_date']) for x in r['rows']}), 36)
        for lane in (*m.LANES, 'INCUMBENT_ADD_ONLY_CONTROL', 'CASH_RETENTION_CONTROL'):
            subset = [x for x in r['rows'] if x['lane'] == lane]
            self.assertEqual([(x['decision_date'], x['execution_date']) for x in subset], m.CLOCK)
            self.assertEqual(subset[-1]['forward_window']['available_after_execution_sessions'], 0)
            for x in subset:
                self.assertFalse(x['fork_executable'])
                tsm = next(s for s in x['securities'] if s['security_id'] == 'TSM')
                self.assertFalse(tsm['identity_interval_certified'])
                self.assertFalse(tsm['provider_binding_verified'])
                self.assertIn('DATED_IDENTITY_NOT_IN_BOUND_LANE_EVIDENCE', tsm['gaps'])
        self.assertFalse(r['point_in_time_verified'])

    def test_consumed_bytes_and_post_assembly_drift_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input.json'; path.write_bytes(b'{}')
            refs = {'one': dict(path=str(path), sha256=m.digest(path))}
            with patch.object(m, 'LOADED', {}), patch.object(m, 'references', return_value=refs), patch.object(m, 'assemble') as assemble:
                path.write_bytes(b'{"changed":true}')
                with self.assertRaises(ValueError): m.build()
                assemble.assert_not_called()
                refs['one']['sha256'] = m.digest(path)
                def drift(*args):
                    path.write_bytes(b'{}'); return {}
                assemble.side_effect = drift
                with self.assertRaises(ValueError): m.build()

    def test_existing_namespace_rejected_before_any_build(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(m, 'OUTPUT', Path(directory)), patch.object(m, 'build') as build:
                with self.assertRaises(ValueError): m.publish()
                build.assert_not_called()
