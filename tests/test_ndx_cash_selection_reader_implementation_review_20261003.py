"""Independent bounded selection-reader counterexamples; no actual evidence IO."""
import copy
import io
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from scripts import ndx_cash_neighbor_selection_independent_readback_20261003 as m
from test_ndx_cash_neighbor_selection_independent_readback_20261003 import fixture


def reseal(rows,s,e):
    blob=b''.join(m.enc(x)+b'\n' for x in rows)
    s['ledger_bytes']=len(blob)
    s['ledger_reference']['sha256']=m.sha(blob)
    e['ledger_reference']=copy.deepcopy(s['ledger_reference'])
    return blob


class Review(unittest.TestCase):
    def test_exact_sub_float_distance_and_fee_then_original_order(self):
        for cheaper in (False,True):
            b,s,e,c,rows=fixture()
            # Distances are exactly equal despite different rational encodings.
            rows[1]['selection_ledger_row']['saved_score']['distance']={'numerator':10**40+1,'denominator':10**40}
            rows[2]['selection_ledger_row']['saved_score']['distance']={'numerator':2*(10**40+1),'denominator':2*10**40}
            if cheaper:
                rows[2]['selection_ledger_row']['saved_score']['fees_usd']={'numerator':1,'denominator':20}
                rows[2]['selection_ledger_row']['saved_plan']['fees_usd']='0.05'
                s['selection']['status']=e['status']='NEW_PATH_REQUIRED'
                s['selection']['reused_path_reference']=None
            s['selection']['selected']=copy.deepcopy(rows[2 if cheaper else 1]['selection_ledger_row'])
            b=reseal(rows,s,e)
            out=m.inspect_case(io.BytesIO(b),s,e,c)
            self.assertEqual(out['selected_merged_candidate_index'],2 if cheaper else 1)

    def test_duplicate_vector_resealed_and_pending_authority_rejected(self):
        b,s,e,c,rows=fixture()
        rows[2]['selection_ledger_row']['buy_shares']={'A':1}
        rows[2]['selection_ledger_row']['saved_plan']['buy_shares']={'A':1}
        b=reseal(rows,s,e)
        with self.assertRaisesRegex(ValueError,'duplicate'):m.inspect_case(io.BytesIO(b),s,e,c)
        for key,value in [('consumption_status','PUBLISHED'),('requires_final_publication',False),('account_executed',0)]:
            b,s,e,c,rows=fixture();s[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.inspect_case(io.BytesIO(b),s,e,c)

    def test_journal_span_binds_all_record_coordinates(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'journal'
            record={'stage':'RAW_RETURNED','sequence':4,'task_id':'a'*64,'payload':{'feasible':False}}
            record['record_sha256']=m.sha(m.enc(record));blob=m.enc(record)+b'\n';p.write_bytes(blob)
            reference=m.ref(p,m.sha(blob))
            loc=dict(source_reference=reference,byte_start=0,byte_stop=len(blob),json_pointer_within_selected_record='/payload',**{k:record[k] for k in ('record_sha256','stage','sequence','task_id')})
            evidence=m.Evidence({str(p):reference['sha256']})
            try:
                self.assertEqual(evidence.span(loc,True),record['payload'])
                for key,value in [('sequence',5),('task_id','b'*64),('stage','POSTCHECK'),('byte_stop',len(blob)-1)]:
                    bad=copy.deepcopy(loc);bad[key]=value
                    with self.subTest(key=key),self.assertRaises(ValueError):evidence.span(bad,True)
            finally:evidence.close()

    def test_paired_rows_full_stream_order_eof_and_source_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'paired.json'
            rows=[{'scenario_id':str(i),'text':'\u4e2d'*25000} for i in range(3)]
            blob=m.enc({'before':[1,2],'rows':rows,'after':{'status':'saved'}})
            p.write_bytes(blob);reference=m.ref(p,m.sha(blob))
            self.assertEqual(list(m.iter_json_rows(reference)),rows)
            with self.assertRaises(ValueError):list(m.iter_json_rows(dict(reference,sha256='0'*64)))
            for bad in (blob[:-1],blob+b'{}',b'{"rows":[],"rows":[]}',b'{"rows":[{"x":1,"x":2}]}'):
                p.write_bytes(bad)
                with self.subTest(size=len(bad)),self.assertRaises(ValueError):list(m.iter_json_rows(m.ref(p,m.sha(bad))))

    def test_old_path_ref_context_and_selected_plan_are_bound(self):
        refs={k:m.ref(k,'a'*64) for k in ('paired','previous')}
        plan={'buy_shares':{'A':1},'fees_usd':'0.1'}
        previous={'selected_candidate_index':0,'scenario_id':'case','input_row':{'amount':'1000'},'input_reference':m.ref('input','b'*64),'evaluation':{'branches':[{'evaluated_plans':[plan]}]},'feasible_scores':[],'closure_records':[]}
        paired={'scenario_id':'case','input_row':previous['input_row'],'input_reference':previous['input_reference'],'topup_context':{k:v for k,v in previous.items() if k not in ('evaluation','closure_records','feasible_scores')},'topup_context_reference':dict(refs['previous'],json_pointer='/rows/2'),'selected_plan':plan,'selected_plan_reference':dict(refs['previous'],json_pointer='/rows/2/evaluation/branches/0/evaluated_plans/0'),'paths':{'candidate':{'daily':[]}}}
        selected={'reference':dict(refs['paired'],json_pointer='/rows/2/paths/candidate'),'scenario_id':'case','selected_candidate_index':0,'buy_shares':{'A':1}}
        m.validate_old_path(selected,paired,previous,2,refs)
        for change in ('pointer','source','plan','context','buys'):
            a,b=copy.deepcopy(selected),copy.deepcopy(paired)
            if change=='pointer':a['reference']['json_pointer']='/rows/39/paths/candidate'
            elif change=='source':a['reference']['path']='unrelated.json'
            elif change=='plan':b['selected_plan']['fees_usd']='0'
            elif change=='context':b['topup_context']['input_row']['amount']='2000'
            else:a['buy_shares']['A']=2
            with self.subTest(change=change),self.assertRaises(ValueError):m.validate_old_path(a,b,previous,2,refs)

if __name__=='__main__':unittest.main()

