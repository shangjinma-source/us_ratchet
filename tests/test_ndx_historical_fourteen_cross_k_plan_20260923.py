import copy
import json
from pathlib import Path
import unittest
from scripts import ndx_historical_fourteen_cross_k_plan_20260923 as m


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document=json.loads(Path(m.INPUT['path']).read_bytes());cls.target=json.loads(Path(m.TARGET['path']).read_bytes())

    def row(self,panel):
        task={k:v for k,v in self.target['task'].items() if k!='task_id'};tickers=[task['selected'][s]['ticker'] for s in sorted(task['selected'])]
        matrix=m.digest(dict(dates=[d.date().isoformat() for d in panel['returns'].index],tickers=tickers,returns=panel['returns'][tickers].to_numpy().tolist()))
        sources=self.target['result']['source_hashes']
        return dict(task=task,task_id=m.digest(task),fit_data_sha256=matrix,input_equivalence_sha256=m.digest(dict(task=task,fit_data_sha256=matrix,fitter_source_hashes=sources)))

    def test_actual_first126_and_completed_structure_no_latest_weights(self):
        panel=m.historical_view(self.document)
        self.assertEqual(panel['returns'].shape,(126,14));self.assertEqual(str(panel['returns'].index[-1].date()),'2026-03-18')
        rows=[self.row(panel)]
        m.attach_completed_reference(rows,self.target,self.target['result']['source_hashes'],panel)
        self.assertFalse(rows[0]['result_reused']);self.assertEqual(rows[0]['completed_external_reference'],m.TARGET)

    def test_completed_reference_rejects_wrong_cutoff_matrix_sources(self):
        for defect in ('date','matrix','sources'):
            panel=m.historical_view(self.document);target=copy.deepcopy(self.target);rows=[self.row(panel)];sources=copy.deepcopy(target['result']['source_hashes'])
            if defect=='date':target['task']['cutoff']='2026-09-17'
            elif defect=='matrix':panel['returns'].iloc[0,0]+=.001
            else:sources[next(iter(sources))]='0'*64
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.attach_completed_reference(rows,target,sources,panel)

    def test_missing_gap_or_shifted_fit_dates_rejected(self):
        for defect in ('gaps','dates'):
            doc=copy.deepcopy(self.document)
            if defect=='gaps':doc['candidate_full_original_provenance'].pop()
            else:doc['prices']['fit_return_dates']=doc['prices']['evaluation_return_dates']
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.historical_view(doc)

    def test_enumerator_keeps_excluded_k_and_historical_cutoff(self):
        panel=m.historical_view(self.document);panel['universe']=panel['universe'].iloc[:4].copy()
        tickers=panel['universe']['ticker'].tolist();panel['returns']=panel['returns'][tickers];panel['nominal_close']=panel['nominal_close'][tickers]
        panel['panel_content_sha256']=m.enumeration.core.panel_digest(panel)
        cards,tasks=m.enumeration.enumerate_inputs(panel,m.target_reader.scalar.PARAMS,{'fitter.py':'a'*64})
        self.assertEqual([c['k'] for c in cards],[1,2,3,4]);self.assertEqual(len(tasks),2)
        self.assertTrue(all(c['necessary_bound_certificates'] for c in cards[:3]));self.assertTrue(all(t['task']['cutoff']=='2026-03-18' for t in tasks))


if __name__=='__main__':unittest.main()
