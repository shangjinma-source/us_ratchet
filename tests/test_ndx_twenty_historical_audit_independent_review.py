"""Independent metadata and numeric corruption tests; no producer or fitter."""
import copy
import unittest
from unittest.mock import patch
from test_ndx_twenty_historical_inputs_independent_audit_20260919 import fixture
from scripts import ndx_twenty_historical_inputs_independent_audit_20260919 as m


class IndependentHistoricalAuditReview(unittest.TestCase):
    def test_channel_evidence_cannot_upgrade_identity_or_action_authentication(self):
        p,raw,rows,evidence=fixture()
        m.audit_channel('NFLX',p,raw,rows,evidence)
        for field in ('provider_identity_authenticated','quote_basis_independently_authenticated','complete_actions_verified'):
            bad=copy.deepcopy(evidence);bad[field]=True
            with self.subTest(field=field),self.assertRaises(ValueError):m.audit_channel('NFLX',p,raw,rows,bad)

    def test_coherent_price_and_return_change_cannot_override_raw_observations(self):
        p,raw,rows,evidence=fixture();bad=copy.deepcopy(p)
        for frame in ('nominal_open','nominal_close'):
            for row in bad[frame]['data']:row[0]*=2
        # All returns still agree internally, but raw nominal levels no longer do.
        with self.assertRaises(ValueError):m.audit_channel('NFLX',bad,raw,rows,evidence)

    def test_metadata_counts_and_error_are_typed_and_recomputed(self):
        p,raw,rows,evidence=fixture()
        for field,value in [('fixed_selected_price_count',True),('decimal_open_close_cells',505),('maximum_absolute_decimal_error','NaN'),('maximum_absolute_decimal_error','-1'),('maximum_absolute_decimal_error','0.01')]:
            bad=copy.deepcopy(evidence);bad[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):m.audit_channel('NFLX',p,raw,rows,bad)
        bad=copy.deepcopy(p);bad['returns']['data'][49][0]=float('nan')
        with self.assertRaises(ValueError):m.audit_channel('NFLX',bad,raw,rows,evidence)

    def test_re_signed_outer_report_cannot_drop_sources_or_upgrade_scope(self):
        expected=dict(schema='TWENTY_HISTORICAL_INPUTS_INDEPENDENT_RAW_DECIMAL_AUDIT_V1',historical_expected_source_hashes={'raw':'a'*64},archive_resolution={'bound':True},producer_build_called=False,pure_assemble_called=False,point_in_time_verified=False)
        with patch.object(m,'build',return_value=expected),patch.object(m,'exclusive_publish',side_effect=AssertionError('No write')):
            m.verify(expected)
            for field in ('source','scope','extra'):
                bad=copy.deepcopy(expected)
                if field=='source':bad['historical_expected_source_hashes']={};bad['archive_resolution']={}
                elif field=='scope':bad['point_in_time_verified']=True
                else:bad['historical_identity_verified']=True
                with self.assertRaises(ValueError):m.publish_verified('unused',bad)


if __name__=='__main__':unittest.main()
