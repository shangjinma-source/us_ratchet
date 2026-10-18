from copy import deepcopy
from fractions import Fraction
import hashlib
import unittest
import test_ndx_multidecision_selected_refit_inputs_research as author
from backtest import ndx_multidecision_selected_refit_inputs_research as m


class IndependentReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.args=author.fixture()

    def test_all_latest_slots_exact_independent_calendar_lookup(self):
        a=deepcopy(self.args);out=m.prepare_selected_cutoff_refit_inputs(**a)
        by={b['coordinate']['security_id']:b for b in a['channel_bindings']}
        for item in out['rows']:
            if item['selected'] is None:continue
            ids=sorted(item['selected']);expected=[]
            for day in item['fit_matrix']['dates']:
                row=[]
                for sid in ids:
                    source=next(r for r in by[sid]['channel']['return_rows'] if r['session']==day)
                    row.append(float(Fraction(source['split_only_return_exact'])))
                expected.append(row)
            self.assertEqual(item['fit_matrix']['returns'],expected)
            self.assertEqual(len(expected),126)
            self.assertEqual(item['fit_data_sha256'],hashlib.sha256(m.enc(item['fit_matrix'])).hexdigest())
            self.assertEqual(item['fit_matrix']['dates'][-1],item['cutoff'])
        self.assertEqual(len(out['full_universe_preserved']),77)
        self.assertEqual(len(out['original_provenance_and_missing']),101)

    def test_same_numeric_identity_keeps_different_lane_locations_and_no_later_prior(self):
        out=m.prepare_selected_cutoff_refit_inputs(**deepcopy(self.args))
        initial=[r for r in out['rows'] if r['status']=='INITIAL_REFIT_INPUTS_MATERIALIZED_NOT_DISPATCHED']
        self.assertEqual(len(initial),4)
        # Fixture gives identical winning composition/spec in each lane.
        self.assertEqual(len({r['numerical_task_id'] for r in initial}),1)
        self.assertEqual(len({r['location_id'] for r in initial}),4)
        for r in initial:
            self.assertIsNone(r['requested_previous_target_weights']);self.assertEqual(r['initial_effective_anchor_strength'],0.)
        later=[r for r in out['rows'] if r['status']=='INPUTS_PREPARED_PRIOR_UNRESOLVED']
        self.assertEqual(len(later),20)
        for r in later:
            self.assertIsNone(r['numerical_task_id']);self.assertIsNone(r['location_id'])
            self.assertFalse(r['prior_value_resolved']);self.assertEqual(r['prior_requirement']['lane'],r['lane'])
        for prior in ({},{'status':'PASS','targets':{}}):
            a=deepcopy(self.args);a['previous_refit_evidence']=prior
            with self.assertRaises(ValueError):m.prepare_selected_cutoff_refit_inputs(**a)

    def test_nonzero_offset_and_missing_slot_no_compression(self):
        a=deepcopy(self.args);b=a['channel_bindings'][0];d=b['channel']['decisions'][-1]
        self.assertGreater(d['price_index_start'],0)
        i=d['price_index_start']+503
        b['channel']['return_rows'][i].update(status='MISSING_RETURN',split_only_return_float=None,split_only_return_exact=None)
        out=m.prepare_selected_cutoff_refit_inputs(**a)
        hits=[r for r in out['rows'][-4:] if b['coordinate']['security_id'] in (r['selected'] or {})]
        self.assertTrue(hits)
        for r in hits:
            self.assertEqual(r['status'],'BLOCKED_LATEST126_SOURCE_SLOTS');self.assertEqual(len(r['fit_matrix']['returns']),126)
            self.assertIsNone(r['numerical_task_id']);self.assertEqual(r['missing_latest_return_slots'][0]['return_index'],i)


if __name__=='__main__':unittest.main()
