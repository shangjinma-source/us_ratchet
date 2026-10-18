import copy,json,unittest
from unittest.mock import patch
from scripts import ndx_september_cutoff_snapshot_independent_readback_20260923 as m
from test_ndx_may_cutoff_snapshot_independent_readback_20260919 import fixture as may_fixture

def fixture():
    q,c,i,v,a=may_fixture();ref=dict(path=str(m.QUEUE),sha256='1'*64)
    i['queue']=ref;v['queue']=ref;a['queue']=ref
    q['historical_cutoff']='2023-08-31';v['result']['historical_cutoff']='2023-08-31';v['result']['queue_sha256']=m.pure.digest(q)
    return q,i,v,a

class SeptemberDraftTests(unittest.TestCase):
    def test_actual_september_queue_126_matrix_no_fitter(self):
        self.assertEqual(m.archive.drift.file_sha(m.QUEUE),m.QUEUE_SHA)
        q=json.loads(m.QUEUE.read_bytes());context=json.loads(m.CONTEXT.read_bytes())
        # September's preference reference is already on the frontier: union 339, not 340.
        self.assertEqual((q['candidate_count'],q['risk_liquidity_frontier_count'],q['user_preference_count']),(339,339,1))
        candidate=next(r for r in q['candidates'] if r['task']['weight_spec']=='equal_weight' and {v['ticker'] for v in r['selected'].values()}=={'AMAT','AVGO','CDNS','GOOG'})
        selected=candidate['selected'];self.assertEqual(len(selected),4)
        decoded=m.pure.decode(context['prepared_inputs']['returns']['payload']);names=[selected[s]['ticker'] for s in sorted(selected)]
        payload=dict(dates=[d[:10] for d in decoded['index'][-126:]],tickers=names,
            returns=[[decoded['column_values'][decoded['columns'].index(t)][i] for t in names] for i in range(len(decoded['index'])-126,len(decoded['index']))])
        fit=dict(weight_spec='equal_weight',fit_start=payload['dates'][0],fit_end='2023-08-31',cutoff='2023-08-31',fit_row_count=126,fit_data_sha256=m.pure.digest(payload),
            targets={s:dict(ticker=r['ticker'],issuer_id=r['issuer_id'],target_weight=.25) for s,r in selected.items()},
            risk_chains_by_security={s:r['risk_chain'] for s,r in selected.items()},declared_parameters={k:v for k,v in q['fit_parameters'].items() if k!='fit_days'},
            previous_target_weights={},surviving_anchor_mass=0.,effective_anchor_strength=0.,anchor_by_security={s:0. for s in selected},declared_constraint_checks=dict.fromkeys(m.CHECKS,True),declared_constraints_passed=True)
        checked=m.pure.inspect_context(context,q,dict(candidate=candidate,refit=fit))
        self.assertEqual(checked['fit_row_count'],126);self.assertEqual(checked['fit_end'],'2023-08-31')
    def test_unsealed_queue_never_reads_or_audits(self):
        with patch.object(m,'QUEUE_SHA',None),patch.object(m,'PLANNED',None):
            with self.assertRaises(ValueError):m.build('not-read','0'*64)
    def test_no_seed_full_queue_and_boolean_risk_gates(self):
        with patch.object(m,'PLANNED',104),patch.object(m,'QUEUE_SHA','1'*64):
            q,i,v,a=fixture();m.validate_task(v,a,q,i,m.validate_index(i,q))
            for defect in ('seed','count','risk','missing'):
                q,i,v,a=fixture()
                if defect=='seed':i['seed']={}
                if defect=='count':i['planned']=True
                if defect=='risk':v['result']['independently_recomputed_five_checks']['MAX_SINGLE_WEIGHT']=1
                if defect=='missing':q['candidates'].pop()
                with self.subTest(defect=defect),self.assertRaises(ValueError):m.validate_task(v,a,q,i,m.validate_index(i,q))
    def test_actual_candidate_context_hash_without_claiming_queue_selection(self):
        self.assertEqual(m.archive.drift.file_sha(m.CONTEXT),m.CONTEXT_SHA)
        context=json.loads(m.CONTEXT.read_bytes())
        decoded=m.pure.decode(context['prepared_inputs']['returns']['payload'])
        self.assertEqual(decoded['index'][-1][:10],'2023-08-31')
        self.assertGreaterEqual(len(decoded['index']),126)
        self.assertNotEqual(m.QUEUE,m.may.QUEUE)

if __name__=='__main__':unittest.main()
