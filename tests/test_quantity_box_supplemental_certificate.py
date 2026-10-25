from copy import deepcopy
from hashlib import sha256
import json
from fractions import Fraction as F
import unittest
from backtest.quantity_integer_box_certificate_prototype import solve
from backtest.quantity_multi_anchor_bound_prototype import bound
from backtest.quantity_box_supplemental_certificate import supplement,verify
from test_quantity_integer_box_certificate_prototype import fixture


def raw(value):return json.dumps(value,sort_keys=True).encode()


def sources(args=None):
    parent=solve(**(args or fixture()),node_budget=1);parent_raw=raw(parent);rows=[];evidence={}
    for n in parent['unsearched_frontier']:
        item=bound(inputs=parent['inputs'],box=n['box'],incumbent=parent['selected']);data=raw(item)
        evidence[n['id']]=data;rows.append(dict(id=n['id'],sha256=sha256(data).hexdigest(),binding_sha256=item['binding_sha256']))
    manifest=raw(dict(rows=rows))
    return dict(parent_raw=parent_raw,expected_parent_sha256=sha256(parent_raw).hexdigest(),expected_input_sha256=parent['input_sha256'],evidence_manifest_raw=manifest,expected_manifest_sha256=sha256(manifest).hexdigest(),evidence_raw_by_id=evidence)


def repack_manifest(a,rows):
    a['evidence_manifest_raw']=raw(dict(rows=rows));a['expected_manifest_sha256']=sha256(a['evidence_manifest_raw']).hexdigest()


class SupplementalTests(unittest.TestCase):
    def test_strict_boolean_integer_authority_and_count_types(self):
        args=fixture();args['training_scenarios']=[{s:'1' for s in 'ABC'}];args['fee_bps']='0'
        a=sources(args);result=supplement(**a)
        for key,value in [('new_search_nodes',False),('objective_value_optimal',1),('data_authenticated',0),('future_performance_guaranteed',0),('parent_ledger_modified',0),('tie_break_optimality_established',0),('parent_processed_nodes',True)]:
            changed=deepcopy(result);changed[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):verify(changed,**a)
        rows=json.loads(a['evidence_manifest_raw'])['rows'];identifier=rows[0]['id']
        ev=json.loads(a['evidence_raw_by_id'][identifier]);ev['executable_portfolio']=0
        a['evidence_raw_by_id'][identifier]=raw(ev);rows[0]['sha256']=sha256(raw(ev)).hexdigest();repack_manifest(a,rows)
        with self.assertRaisesRegex(ValueError,'STRICT_EVIDENCE'):supplement(**a)

    def test_complete_equal_bounds_close_value_not_tie(self):
        args=fixture();args['training_scenarios']=[{s:'1' for s in 'ABC'}];args['fee_bps']='0'
        a=sources(args);parent_before=a['parent_raw'];result=supplement(**a)
        self.assertTrue(result['objective_value_optimal']);self.assertFalse(result['tie_break_optimality_established'])
        self.assertEqual(len(result['closed_nodes']),2);self.assertEqual(a['parent_raw'],parent_before)
        verify(json.loads(raw(result)),**a)

    def test_insufficient_bound_stays_in_frontier(self):
        a=sources();result=supplement(**a)
        self.assertTrue(result['remaining_frontier']);self.assertFalse(result['objective_value_optimal'])
        for row in result['remaining_frontier']:self.assertGreater(F(row['supplemental_bound']['upper_product']),F(result['lower_product']))
        changed=deepcopy(result);changed['remaining_frontier']=[];changed['objective_value_optimal']=True
        with self.assertRaises(ValueError):verify(changed,**a)

    def test_missing_duplicate_wrong_box_input_and_hash(self):
        for kind in ('missing','duplicate','box','input','incumbent','raw','manifest','parent'):
            a=sources();rows=json.loads(a['evidence_manifest_raw'])['rows']
            if kind=='missing':rows.pop();repack_manifest(a,rows)
            elif kind=='duplicate':rows.append(rows[0]);repack_manifest(a,rows)
            elif kind in ('box','input','incumbent'):
                identifier=rows[0]['id'];ev=json.loads(a['evidence_raw_by_id'][identifier])
                if kind=='box':ev['binding']['box']['A']=[0,100]
                elif kind=='input':ev['binding']['inputs']['entered_cash']='99'
                else:ev['binding']['incumbent']={'A':1}
                a['evidence_raw_by_id'][identifier]=raw(ev);rows[0]['sha256']=sha256(raw(ev)).hexdigest();repack_manifest(a,rows)
            elif kind=='raw':a['evidence_raw_by_id'][rows[0]['id']]+=b' '
            elif kind=='manifest':a['evidence_manifest_raw']+=b' '
            else:a['parent_raw']+=b' '
            with self.subTest(kind=kind),self.assertRaises(ValueError):supplement(**a)

if __name__=='__main__':unittest.main()
