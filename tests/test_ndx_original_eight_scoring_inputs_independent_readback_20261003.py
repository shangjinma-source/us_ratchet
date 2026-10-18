from copy import deepcopy
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from scripts import ndx_original_eight_scoring_inputs_independent_readback_20261003 as m
from test_ndx_original_eight_scoring_inputs_20261003 import fixture as parents

def fixture():
    docs,refs=parents();args=m.inspect_parent_bindings(docs,refs);base={'fixed':'a'*64}
    docs['index'].update(original_provenance_and_missing=[{'old':i} for i in range(101)],preserved_evidence_sidecars={'seven':'preserved'});docs['tsm']['complete_tsm_metadata']={'original':'kept'}
    document=dict(schema='ORIGINAL_EIGHT_SCORING_INPUTS_DOCUMENT_V1',status='PUBLISHED_FIXED_DAILY_WEIGHT_RETURNS_PENDING_INDEPENDENT_READBACK',input_references=refs,source_hashes=base,raw_channel_reconstruction_count=0,new_numeric_readback_completed=False,shared_source_provenance=dict(original101=docs['index']['original_provenance_and_missing'],seven_sidecars=docs['index']['preserved_evidence_sidecars'],tsm_metadata=docs['tsm']['complete_tsm_metadata']),runtime=dict(pandas=m.pd.__version__,numpy=m.np.__version__),scoring_inputs=dict(original_control_preserved=args['original_control']),**dict.fromkeys(m.FLAGS,False))
    pub=dict(schema='ORIGINAL_EIGHT_SCORING_INPUTS_PUBLICATION_V1',status=document['status'],input_references=refs,source_hashes=base,**dict.fromkeys(m.FLAGS,False));started=dict(schema='ORIGINAL_EIGHT_SCORING_INPUTS_STARTED_V1',input_references=refs,source_hashes=base,retry_allowed=False)
    return document,pub,started,docs,refs,base,args

class Tests(unittest.TestCase):
    def test_full_evidence_and_source_claim_attacks(self):
        a=fixture();m.inspect_document(*a)
        for key,value in [('source_hashes',{}),('raw_channel_reconstruction_count',False),('point_in_time_verified',True),('shared_source_provenance',{})]:
            b=deepcopy(a);b[0][key]=value
            with self.assertRaises(ValueError):m.inspect_document(*b)
    def test_role_and_audit_swaps(self):
        d,r=parents();d['index_audit']['rows'][0]['channel_reference']={'path':'wrong','sha256':'c'*64}
        with self.assertRaises(ValueError):m.inspect_parent_bindings(d,r)
    def test_future_before_io_and_parent_extra(self):
        with patch.object(m,'INPUTS_SHA',None), patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
            with self.assertRaisesRegex(ValueError,'Pending'):m.readback(execute=True)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            for name in ('started.json','inputs.json','publication.json','extra'):(p/name).write_bytes(b'{}')
            with patch.object(m,'PARENT',p):
                with self.assertRaisesRegex(ValueError,'Exact'):m.guard({})
