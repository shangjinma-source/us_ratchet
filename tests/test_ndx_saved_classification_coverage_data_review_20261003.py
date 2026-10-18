from copy import deepcopy
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
from scripts import ndx_saved_classification_coverage_20261003 as m
from test_ndx_saved_classification_coverage_20261003 import evidence
from test_ndx_saved_risk_classification_coverage_research import fixture

def disk_fixture(root):
    args=fixture();docs,blobs,refs=evidence()
    docs['wiring']=args['wiring'];docs['training_panel']=args['training_panel']
    for k in ('wiring','training_panel'):docs[k]['source_hashes']={'old_parent_claim':'a'*64}
    records={}
    def put(role,value):
        path=root/(role+('.json' if not isinstance(value,bytes) else '.bin'));data=value if isinstance(value,bytes) else m.encode(value);path.write_bytes(data)
        records[role]=(str(path),m.digest(data));return dict(path=str(path),sha256=m.digest(data))
    for k in ('wiring_reader','training_reader'):refs[k]=put(k,b'# synthetic reader identity')
    for k in ('wiring','training_panel'):refs[k]=put(k,docs[k])
    for pub,k,field in [('wiring_publication','wiring','wiring_reference'),('training_publication','training_panel','panel_reference')]:
        docs[pub][field]=refs[k];docs[pub]['source_hashes']=docs[k]['source_hashes'];refs[pub]=put(pub,docs[pub])
    audit=docs['training_audit']
    for field,k in [('panel_sha256','training_panel'),('publication_sha256','training_publication'),('reader_sha256','training_reader')]:audit[field]=refs[k]['sha256']
    put('training_audit',audit)
    put('wiring_review_report',('PASS '+' '.join(refs[k]['sha256'] for k in ('wiring','wiring_publication','wiring_reader'))).encode())
    core=Path(m.ROOT/m.BOUND['core'][0]);records['core']=(str(core),m.digest(core.read_bytes()))
    return records

class Tests(unittest.TestCase):
    def test_private_compile_complete_denominator_and_original_claim_scope(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);bound=disk_fixture(root);out=root/'output'
            poison=types.SimpleNamespace(summarize_saved_classification=lambda **k:(_ for _ in ()).throw(AssertionError('Cached core must not run')))
            with patch.object(m,'BOUND',bound),patch.object(m,'OUTPUT',out),patch.dict('sys.modules',{'backtest.ndx_saved_risk_classification_coverage_research':poison}):
                r=m.run(execute=True);d=m.parse(Path(r['path']).read_bytes())
                self.assertEqual(len(d['source_hashes']),10);self.assertEqual(len(d['coverage']['rows']),101)
                self.assertEqual(d['coverage']['counts']['training_selected_security_count'],77)
                self.assertEqual(d['coverage']['counts']['unknown_label_rows'],23)
                self.assertEqual(d['wiring_audit_evidence_type'],'SAVED_REPORT_AND_READER_NOT_NEW_MACHINE_ATTESTATION')
                self.assertFalse(d['full_transitive_source_closure_reverified']);self.assertFalse(d['official_classification_conflict_audited'])
                self.assertEqual(d['parent_source_hashes_preserved']['wiring'],{'old_parent_claim':'a'*64})
    def test_late_source_and_output_drift_keep_failed_namespace(self):
        for mode in ('source','output'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as td:
                root=Path(td);bound=disk_fixture(root);out=root/'output';real=m.save
                def mutate(path,value):
                    r=real(path,value)
                    if path.name=='publication.json':
                        target=Path(bound['training_reader'][0]) if mode=='source' else out/'coverage.json'
                        target.write_bytes(b'changed')
                    return r
                with patch.object(m,'BOUND',bound),patch.object(m,'OUTPUT',out),patch.object(m,'save',side_effect=mutate):
                    with self.assertRaises(ValueError):m.run(execute=True)
                    self.assertTrue((out/'failure.json').exists())
                    with patch.object(Path,'read_bytes',side_effect=AssertionError('No retry reads')):
                        with self.assertRaises(ValueError):m.run(execute=True)
    def test_failed_receipts_exact_integer_zero_and_unverified_flags(self):
        for mode in ('receipt','zero','legal','md'):
            docs,blobs,refs=evidence()
            if mode=='receipt':docs['wiring_publication']['status']='FAILED'
            elif mode=='zero':docs['training_audit']['evaluation_numeric_fields_in_fit_payload']=False
            elif mode=='legal':docs['training_audit']['legal_training_input_admitted']=0
            else:blobs['wiring_review_report']=blobs['wiring_review_report'].replace(refs['wiring_reader']['sha256'].encode(),b'other')
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.validate_evidence(docs,blobs,refs)

if __name__=='__main__':unittest.main()
