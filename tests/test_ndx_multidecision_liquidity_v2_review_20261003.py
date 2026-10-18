"""Recovery-version narrow encoding tests; never executes saved-data probe."""
from copy import deepcopy
from decimal import localcontext, Inexact
import unittest
from test_ndx_multidecision_liquidity_inputs_v2_research import fixture, m


def split_pair():
    saved={'1781271000':dict(date=1781271000,numerator='10.0',denominator='1.0',splitRatio='10:1')}
    bridge={'1781271000':dict(date=1781271000,numerator=10.0,denominator=1.0,splitRatio='10:1')}
    return saved,bridge


class V2Review(unittest.TestCase):
    def test_exact_decimal_encoding_never_ratio_only_or_coerce_dates(self):
        saved,bridge=split_pair();before=deepcopy((saved,bridge))
        with localcontext() as context:
            context.prec=2;context.traps[Inexact]=True
            m.compare_split_representations(saved,bridge,m.ENCODING)
        self.assertEqual((saved,bridge),before)
        attacks=[lambda s,b:s['1781271000'].update(numerator='20.0',denominator='2.0'),
                 lambda s,b:s['1781271000'].update(date=1781271000.0),
                 lambda s,b:s['1781271000'].update(numerator='10.00000000000000000001'),
                 lambda s,b:s['1781271000'].update(numerator='Infinity'),
                 lambda s,b:b['1781271000'].update(denominator=True),
                 lambda s,b:b['1781271000'].update(numerator=10),
                 lambda s,b:s['1781271000'].update(splitRatio='20:2')]
        for change in attacks:
            s,b=split_pair();change(s,b)
            with self.assertRaises(ValueError):m.compare_split_representations(s,b,m.ENCODING)

    def test_future_encoded_split_stays_unknown_with_both_original_objects(self):
        a=fixture();c=a['channels_document']['rows'][0]['channel'];saved,bridge=split_pair()
        c['returned_events']['splits']=deepcopy(saved);c['bridge_row_preserved']['new_returned_splits']=deepcopy(bridge)
        policy=dict(session='2026-06-12',kind='ORDINARY_SPLIT',numerator=10,denominator=1)
        c['event_policies']=[policy];c['bridge_row_preserved']['event_policy_bridge']['events']=[dict(session=policy['session'],provider_event_key='1781271000',policy=deepcopy(policy))]
        original=deepcopy(a);out=m.prepare_decision_liquidity(**a)
        row=out['periods'][0]['rows'][0]
        self.assertEqual(row['status'],'UNKNOWN_LIQUIDITY');self.assertIsNone(row['conditional_numerical_threshold_passed'])
        evidence=out['channel_action_and_source_evidence'][0]
        self.assertEqual(evidence['returned_events']['splits'],saved)
        self.assertEqual(evidence['bridge_row_preserved']['new_returned_splits'],bridge)
        self.assertEqual(a,original)
        self.assertTrue(all(out[key] is False for key in m.FLAGS))

    def test_recovery_scope_and_each_prior_ref_conflict(self):
        a=fixture();out=m.prepare_decision_liquidity(**a)
        self.assertEqual(out['schema'],'CONDITIONAL_MULTIDECISION_LIQUIDITY_INPUTS_V2')
        self.assertIn('WRAPPER_MUST_AUTHENTICATE_PRIOR_BYTES',out['recovery_semantics'])
        for role,r in m.RECOVERY_REFERENCES.items():
            self.assertEqual(out['source_hash_declarations'][r['path']],r['sha256'])
            b=deepcopy(a);b['channels_document']['source_hashes'][r['path']]='0'*64
            with self.subTest(role=role),self.assertRaises(ValueError):m.prepare_decision_liquidity(**b)


if __name__=='__main__':unittest.main()
