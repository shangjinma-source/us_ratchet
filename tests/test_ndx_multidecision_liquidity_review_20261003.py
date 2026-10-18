"""Independent exact-order statistics and inventory/closure attacks; synthetic only."""
from copy import deepcopy
from decimal import localcontext
from fractions import Fraction
import unittest

from test_ndx_multidecision_liquidity_inputs_research import fixture, add_event, m


def rehash(a):
    for row in a['channels_document']['rows']:
        row['channel']['quote_rows_sha256'] = m.digest(row['channel']['quote_rows'])


class LiquidityReview(unittest.TestCase):
    def test_full_77_security_inventory_keeps_two_classes_and_all_evidence(self):
        a=fixture();s=a['channels_document'];template=deepcopy(s['rows'][-1])
        for i in range(4,77):
            row=deepcopy(template);row['coordinate'].update(security_id=f'S{i:03d}',issuer_id=f'I{i:03d}',ticker=f'T{i:03d}')
            c=row['channel'];c['ticker']=f'T{i:03d}'
            for key,bridgekey in [('raw_reference','new_raw_reference'),('receipt_reference','new_receipt_reference')]:
                c[key]=dict(path=key+str(i),sha256=('a' if key=='raw_reference' else 'b')*64)
                c['bridge_row_preserved'][bridgekey]=deepcopy(c[key]);s['source_hashes'][c[key]['path']]=c[key]['sha256']
            s['rows'].append(row)
        s.update(security_count=77,issuer_count=76,conditional_numeric_channel_count=77)
        a['full_inventory']=[{k:r['coordinate'][k] for k in ('security_id','issuer_id','ticker')} for r in s['rows']]
        out=m.prepare_decision_liquidity(**a)
        for period in out['periods']:
            self.assertEqual(period['security_denominator'],77)
            self.assertEqual([r['coordinate']['security_id'] for r in period['rows']],[r['security_id'] for r in a['full_inventory']])
        self.assertEqual(out['original_provenance_and_missing'],s['original_provenance_and_missing'])
        self.assertEqual(out['preserved_evidence_sidecars'],s['preserved_evidence_sidecars'])
        self.assertTrue(all(out[k] is False for k in m.FLAGS))

    def test_permuted_exact_median_and_causal_window_not_saved_september_mdv(self):
        a = fixture(); s = a['channels_document']; c = s['rows'][0]['channel']
        cutoff = a['decision_contract']['document']['decisions'][0]['decision_date']
        j = s['calendar253'].index(cutoff)
        values = [Fraction(50000000) + Fraction(i-31, 7) for i in range(63)]
        for offset in range(63):
            volume = offset+1
            c['quote_rows'][j-62+offset].update(nominal_close_exact=str(values[(offset*17)%63]/volume), raw_volume=volume)
        s['rows'][0]['coordinate']['median_dollar_volume_usd'] = 1
        rehash(a); before = deepcopy(a)
        with localcontext() as context:
            context.prec = 2
            result = m.prepare_decision_liquidity(**a)
        r = result['periods'][0]['rows'][0]
        self.assertEqual(r['median_dollar_volume_exact'], '50000000')
        self.assertIs(r['conditional_numerical_threshold_passed'], True)
        self.assertEqual(r['required_dates'], s['calendar253'][j-62:j+1])
        self.assertEqual(a, before)
        c['quote_rows'][j-63].update(nominal_close_exact='1',raw_volume=1)
        c['quote_rows'][j+1].update(nominal_close_exact='99999999999999999999999',raw_volume=1)
        rehash(a)
        self.assertEqual(m.prepare_decision_liquidity(**a)['periods'][0]['rows'][0], r)

    def test_split_start_boundary_and_after_cutoff_are_both_unknown(self):
        original = fixture(); cal = original['channels_document']['calendar253']
        j = cal.index(original['decision_contract']['document']['decisions'][0]['decision_date'])
        for session, blocked in [(cal[j-63],False),(cal[j-62],True),(cal[-1],True)]:
            a = deepcopy(original);add_event(a,session)
            r = m.prepare_decision_liquidity(**a)['periods'][0]['rows'][0]
            self.assertEqual(r['status']=='UNKNOWN_LIQUIDITY',blocked)
            if blocked:
                self.assertIsNone(r['median_dollar_volume_exact'])
                self.assertIsNone(r['conditional_numerical_threshold_passed'])
                self.assertEqual(len(r['affecting_returned_splits']),1)
        a=deepcopy(original);add_event(a,cal[1]);c=a['channels_document']['rows'][0]['channel']
        p=dict(session=cal[2],kind='ORDINARY_SPLIT',numerator=25,denominator=1)
        c['event_policies'].append(p)
        c['returned_events']['splits']['unmapped']=dict(numerator=2,denominator=1)
        c['bridge_row_preserved']['new_returned_splits']=deepcopy(c['returned_events']['splits'])
        c['bridge_row_preserved']['event_policy_bridge']['events'].append(dict(session=cal[2],provider_event_key='event',policy=p))
        with self.assertRaises(ValueError):m.prepare_decision_liquidity(**a)

    def test_missing_is_not_zero_and_invalid_types_never_qualify(self):
        a=fixture();j=a['channels_document']['calendar253'].index(a['decision_contract']['document']['decisions'][0]['decision_date'])
        for value in (None,False,0,1.0,-1):
            b=deepcopy(a);b['channels_document']['rows'][0]['channel']['quote_rows'][j]['raw_volume']=value;rehash(b)
            if value is None:
                out=m.prepare_decision_liquidity(**b);p=out['periods'][0]
                self.assertEqual(len(p['rows']),len(a['full_inventory']))
                self.assertEqual(p['unknown_count'],1);self.assertIn('MISSING_RAW_VOLUME',p['rows'][0]['reasons'])
                self.assertEqual(len(out['original_provenance_and_missing']),101);self.assertEqual(len(out['preserved_evidence_sidecars']),7)
            else:
                with self.subTest(value=value),self.assertRaises(ValueError):m.prepare_decision_liquidity(**b)

    def test_nested_source_declarations_and_sidecar_binding(self):
        a=fixture();d=a['decision_contract']['document']
        d['selection_contract_reference']=dict(path='selection',sha256='1'*64)
        d['search_budget_reference']=dict(path='budget',sha256='2'*64)
        out=m.prepare_decision_liquidity(**a)
        for r in (d['rule_reference'],d['selection_contract_reference'],d['search_budget_reference']):
            self.assertEqual(out['source_hash_declarations'][r['path']],r['sha256'])
        b=deepcopy(a);b['channels_document']['source_hashes']['selection']='3'*64
        with self.assertRaises(ValueError):m.prepare_decision_liquidity(**b)
        for key in ('json_pointer','sha256','path'):
            b=deepcopy(a);r=next(iter(b['channels_document']['preserved_sidecar_references'].values()))
            r[key]={'json_pointer':'/wrong','sha256':'4'*64,'path':'wrong'}[key]
            with self.subTest(key=key),self.assertRaises(ValueError):m.prepare_decision_liquidity(**b)


if __name__=='__main__':unittest.main()
