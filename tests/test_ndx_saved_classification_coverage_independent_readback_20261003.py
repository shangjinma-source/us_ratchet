import unittest
from copy import deepcopy
from pathlib import Path
import tempfile
from unittest.mock import patch
from scripts import ndx_saved_classification_coverage_independent_readback_20261003 as m
from test_ndx_saved_risk_classification_coverage_research import fixture,core
from test_ndx_saved_classification_coverage_data_review_20261003 import disk_fixture
from scripts import ndx_saved_classification_coverage_20261003 as producer

def case():
    args=fixture();out=core.summarize_saved_classification(**args)
    refs={k:{n:v for n,v in args[k+'_reference' if k=='wiring' else 'training_reference'].items() if n!='json_pointer'} for k in ('wiring','training_panel')}
    return out,args['wiring'],args['training_panel'],refs

class Tests(unittest.TestCase):
    def test_all101_separate78_77_unknown_and_historical(self):
        args=case();before=deepcopy(args);d=m.inspect(*args)
        self.assertEqual(args,before);self.assertEqual(d['counts']['coordinate_security_count'],78);self.assertEqual(d['counts']['training_selected_security_count'],77);self.assertEqual(d['counts']['unknown_label_rows'],23);self.assertEqual(d['historical_denominator_rows'],15)
    def test_preserved_pointer_reason_count_bool_and_full_sidecars(self):
        for mode in ('row','pointer','reason','count','history','late'):
            args=case();out=args[0]
            if mode=='row':out['rows'][0]['original_wiring_row']['risk_chain']='invented'
            elif mode=='pointer':out['rows'][0]['local_evidence']['bulk_extended_provenance_reference']['reference']['json_pointer']='/bulk_extended_provenance/1'
            elif mode=='reason':out['rows'][77]['nonselection_evidence']=[]
            elif mode=='count':out['counts']['formally_verified_rows']=False
            elif mode=='history':out['saved_wiring_scope']['historical_denominators_preserved'].pop()
            else:out['saved_training_scope']['original_identity_assumed_window']['first']='2020-01-01'
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.inspect(*args)
    def test_shared_issuer_review_not_certified_reclassification(self):
        a=fixture();a['wiring']['rows'][1]['risk_chain']='consumer';a['training_panel']['panel']['fit_payload']['selected_by_security']['security:1']['risk_chain']='consumer'
        out=core.summarize_saved_classification(**a);refs=dict(wiring={k:v for k,v in a['wiring_reference'].items() if k!='json_pointer'},training_panel={k:v for k,v in a['training_reference'].items() if k!='json_pointer'})
        self.assertEqual(m.inspect(out,a['wiring'],a['training_panel'],refs)['issuer_label_review_count'],1)
        out['issuer_label_reviews'][0]['certified_classification_conflict']=True
        with self.assertRaises(ValueError):m.inspect(out,a['wiring'],a['training_panel'],refs)
    def test_synthetic_full_source_wrapper_and_no_repeat(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);bound=disk_fixture(root);parent=root/'published';audit=root/'audit'
            with patch.object(producer,'BOUND',bound),patch.object(producer,'OUTPUT',parent):r=producer.run(execute=True)
            pub=parent/'publication.json';h=m.sha(pub.read_bytes())
            with patch.object(m,'BOUND',bound),patch.object(m,'PARENT',parent),patch.object(m,'OUTPUT',audit),patch.object(m,'COVERAGE_SHA',r['sha256']),patch.object(m,'PUBLICATION_SHA',h):
                answer=m.readback(execute=True);d=m.loads(Path(answer['path']).read_bytes());self.assertEqual(d['status'],'PASS');self.assertFalse(d['core_called'])
                with patch.object(Path,'read_bytes',side_effect=AssertionError('No retry read')):
                    with self.assertRaises(ValueError):m.readback(execute=True)
    def test_pending_pins_before_any_read(self):
        with tempfile.TemporaryDirectory() as td, patch.object(m,'OUTPUT',Path(td)/'audit'), patch.object(m,'COVERAGE_SHA',None),patch.object(m,'PUBLICATION_SHA',None),patch.object(Path,'read_bytes',side_effect=AssertionError('No I/O')):
            with self.assertRaisesRegex(ValueError,'Pending'):m.readback(execute=True)
if __name__=='__main__':unittest.main()
