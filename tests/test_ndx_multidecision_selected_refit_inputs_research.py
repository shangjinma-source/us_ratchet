from copy import deepcopy
from fractions import Fraction
import unittest
from backtest import ndx_multidecision_selected_refit_inputs_research as m
from backtest import ndx_registered_scoring_selector_adapter_research as adapter
from backtest import ndx_full_ndx_multidecision_selector_research as selector
from test_ndx_registered_scoring_selector_adapter_research import fixture as selection_fixture


def fixture():
    a=selection_fixture();prepared=adapter.assemble_registered_selector_inputs(**a);saved=selector.select_full_ndx_lanes(registration=prepared['registration'],records=prepared['records'])
    def ref(name):return dict(path='/synthetic/'+name,sha256=m.digest(name))
    sr=ref('selection_raw');rr=ref('selection_reader');selection=dict(document=saved,reference=sr,reader_reference=rr,readback_reference=ref('selection_audit'),readback=dict(schema='REGISTERED_SCORING_SELECTION_INDEPENDENT_READBACK_V1',status='PASS',reader_sha256=rr['sha256'],raw_selection_reference=sr,source_hashes={sr['path']:sr['sha256'],rr['path']:rr['sha256']},ranking_inspection=dict(status='PASS',coordinate_count=12)))
    u=a['budget_plan']['full_universe_preserved'];days=sorted({d for r in a['budget_plan']['decision_inputs_preserved'] for d in r['scoring_price_dates']});quotes=[];bindings=[];sourcehash={};rows=[];auditrows=[]
    needed={sid for row in saved['rows'] for c in row['choices'] if c['selected'] for sid in c['selected']['record_preserved']['task']['security_ids']}
    for i,coord in enumerate(u):
        r=ref('channel_'+str(i));row=dict(index=i,coordinate=deepcopy(coord),channel_reference=r);rows.append(row);auditrows.append(dict(row,inspection={'status':'PASS'}));sourcehash[r['path']]=r['sha256']
        if coord['security_id'] not in needed:continue
        returns=[]
        for n in range(len(days)-1):
            exact=str(Fraction((i+1)*1000+n+1,10000000));returns.append(dict(previous_session=days[n],session=days[n+1],status='CONDITIONAL_NUMERIC_SLOT',split_only_return_exact=exact,split_only_return_float=float(Fraction(exact)),dividends_included=False))
        decisions=[]
        for d in a['budget_plan']['decision_inputs_preserved']:
            pd=d['scoring_price_dates'];start=days.index(pd[0]);decisions.append(dict(cutoff=d['cutoff'],required_price_dates=pd,price_index_start=start,price_index_stop=start+505))
        ch=dict(schema='MULTIDECISION_SCORING_HISTORY_CHANNEL_V1',ticker=coord['ticker'],decisions=decisions,return_rows=returns,**dict.fromkeys(('point_in_time_verified','fit_performed','score_computed','missing_or_blocked_slots_dropped','unequal_window_pooling_allowed'),False));bindings.append(dict(coordinate=deepcopy(coord),reference=r,channel=ch))
    h=ref('history');hr=ref('history_reader');sourcehash.update({h['path']:h['sha256'],hr['path']:hr['sha256']});counts=dict(security_count=77,issuer_count=76,observed_security_count=101,preserved_sidecar_count=7)
    history=dict(document=dict(schema='MULTIDECISION_SCORING_HISTORY_AGGREGATE_V1',rows=rows,original_provenance_and_missing=[{'row':n} for n in range(101)],preserved_evidence_sidecars={str(n):{'preserved':n} for n in range(7)},**counts),reference=h,reader_reference=hr,readback_reference=ref('history_audit'),readback=dict(schema='MULTIDECISION_SCORING_HISTORY_INDEPENDENT_READBACK_V2',status='PASS',index_reference=h,reader_sha256=hr['sha256'],source_hashes=sourcehash,rows=auditrows,**counts))
    fs={'/code/'+name:sha for name,sha in m.FITTER_CODES.items()};entry='/code/ndx_dynamic_cutoff_refit_v2_research.py'
    fitter=dict(schema='OUTER_CUTOFF_REFIT_SOURCE_CONTRACT_V1',parameters=deepcopy(m.PARAMETERS),reference=ref('outer_fitter_manifest'),entrypoint_function='refit_dynamic_cutoff_weights',entrypoint_reference=dict(path=entry,sha256=fs[entry]),source_hashes=fs,fitter_source_fingerprint=m.digest(fs),source_bytes_authenticated=False,fit_performed=False,execution_authorized=False,promotion_allowed=False)
    return dict(selection=selection,history=history,channel_bindings=bindings,fitter_contract=fitter,previous_refit_evidence=None)

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.args=fixture()

    def test_full48_latest126_original_order_identity_and_prior_unknown(self):
        out=m.prepare_selected_cutoff_refit_inputs(**self.args)
        self.assertEqual(out['coordinate_count'],48);self.assertEqual(out['status_counts'],{'SOURCE_BLOCKED':24,'INITIAL_REFIT_INPUTS_MATERIALIZED_NOT_DISPATCHED':4,'INPUTS_PREPARED_PRIOR_UNRESOLVED':20})
        first=out['rows'][4];self.assertEqual(first['fit_matrix']['dates'][-1],'2026-03-31');self.assertEqual(len(first['fit_matrix']['dates']),126)
        self.assertEqual(list(first['selected']),sorted(first['selected']));self.assertEqual(first['numerical_identity']['requested_previous_target_weights'],None);self.assertEqual(first['initial_effective_anchor_strength'],0.)
        source=self.args['channel_bindings'][0];off=source['channel']['decisions'][0]['price_index_start'];sid=source['coordinate']['security_id'];column=list(first['selected']).index(sid)
        self.assertEqual(first['fit_matrix']['returns'][0][column],source['channel']['return_rows'][off+378]['split_only_return_float'])
        later=out['rows'][12];self.assertIsNone(later['numerical_task_id']);self.assertFalse(later['prior_value_resolved']);self.assertEqual(later['prior_requirement']['previous_cutoff'],'2026-03-31');self.assertEqual(len(later['fit_matrix']['returns']),126)
        self.assertEqual(len(out['original_provenance_and_missing']),101);self.assertEqual(len(out['preserved_evidence_sidecars']),7)
        self.assertFalse(out['fit_performed']);self.assertFalse(out['source_bytes_authenticated'])

    def test_scoring_weights_earlier_history_and_future_values_not_first_fit(self):
        original=m.prepare_selected_cutoff_refit_inputs(**self.args);a=deepcopy(self.args)
        for b in a['channel_bindings']:
            off=b['channel']['decisions'][0]['price_index_start']
            for index in (off,off+377,off+504):
                b['channel']['return_rows'][index]['split_only_return_float']=.25;b['channel']['return_rows'][index]['split_only_return_exact']='1/4'
        changed=m.prepare_selected_cutoff_refit_inputs(**a)
        self.assertEqual(original['rows'][4]['fit_matrix'],changed['rows'][4]['fit_matrix']);self.assertEqual(original['rows'][4]['numerical_task_id'],changed['rows'][4]['numerical_task_id'])

    def test_missing_latest_slot_preserved_and_false_indices_rejected(self):
        a=deepcopy(self.args);c=a['channel_bindings'][0]['channel'];off=c['decisions'][0]['price_index_start'];c['return_rows'][off+400].update(status='BLOCKED_SLOT',split_only_return_float=None,split_only_return_exact=None)
        out=m.prepare_selected_cutoff_refit_inputs(**a);r=out['rows'][4];self.assertEqual(r['status'],'BLOCKED_LATEST126_SOURCE_SLOTS');self.assertEqual(len(r['fit_matrix']['returns']),126);self.assertIsNone(r['numerical_task_id']);self.assertEqual(len(r['missing_latest_return_slots']),1)
        a=deepcopy(self.args);a['channel_bindings'][0]['channel']['decisions'][0]['price_index_start']=False
        with self.assertRaises(ValueError):m.prepare_selected_cutoff_refit_inputs(**a)

    def test_prior_injection_crosslink_and_exact_return_attacks(self):
        for attack in ('weights','pass_ref','audit','return','fitter'):
            a=deepcopy(self.args)
            if attack=='weights':a['previous_refit_evidence']={'S0':1.}
            elif attack=='pass_ref':a['previous_refit_evidence']={'status':'PASS','reference':{'path':'fake','sha256':'a'*64}}
            elif attack=='audit':a['history']['readback']['rows'][0]['channel_reference']['sha256']='b'*64
            elif attack=='return':
                c=a['channel_bindings'][0]['channel'];c['return_rows'][c['decisions'][0]['price_index_start']+400]['split_only_return_float']=True
            else:a['fitter_contract']['source_hashes']['/code/ndx_dynamic_cutoff_refit_v2_research.py']='a'*64;a['fitter_contract']['fitter_source_fingerprint']=m.digest(a['fitter_contract']['source_hashes'])
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.prepare_selected_cutoff_refit_inputs(**a)

    def test_output_does_not_alias_caller_evidence(self):
        a=deepcopy(self.args);before=m.digest(a);out=m.prepare_selected_cutoff_refit_inputs(**a);out['rows'][4]['location_identity']['history_reference']['path']='changed';out['original_provenance_and_missing'][0]['row']=-1
        self.assertEqual(m.digest(a),before)

if __name__=='__main__':unittest.main()
