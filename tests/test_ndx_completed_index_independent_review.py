"""Metadata-only adversarial index review; never refit or rerun task readback."""
from copy import deepcopy
import hashlib
import tempfile
from pathlib import Path
import unittest
import test_ndx_new_cutoff_completed_task_index_20260924 as owner
from scripts import ndx_new_cutoff_completed_task_index_20260924 as m


class IndependentReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        owner.Tests.setUpClass()
        cls.documents=owner.Tests.documents;cls.evidence=owner.Tests.evidence

    def test_original_counter_types(self):
        for attack in ('combination','fitter_count'):
            docs=deepcopy(self.documents)
            if attack=='combination':docs['materialized']['materialization']['combination_count']=True
            else:docs['materialization_audit']['actual_fitter_invocation_count']=False
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(docs,self.evidence)

    def test_five_named_original_risks_not_any_five_booleans(self):
        evidence=deepcopy(self.evidence);checks=evidence[next(iter(evidence))]['audit']['detail']['checks']
        checks['INVENTED_CHECK']=checks.pop(next(iter(checks)))
        with self.assertRaises(ValueError):m.assemble(self.documents,evidence)

    def test_full_denominator_and_external_paths_cannot_shrink_or_move(self):
        docs=deepcopy(self.documents);docs['plan']['plan']['planned_canonical_task_count']=3
        with self.assertRaises(ValueError):m.assemble(docs,self.evidence)
        evidence=deepcopy(self.evidence);saved=evidence[next(iter(evidence))]['audit']
        saved['raw_reference']['path']='other/raw.json'
        with self.assertRaises(ValueError):m.assemble(self.documents,evidence)

    def test_hard_byte_loader_rejects_duplicate_keys_and_digest_substitution(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'duplicate.json';raw=b'{"x":1,"x":2}';path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError,'Duplicate'):
                m.load_bound(dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest()),{})
            with self.assertRaisesRegex(ValueError,'bytes differ'):
                m.load_bound(dict(path=str(path),sha256='0'*64),{})


if __name__=='__main__':unittest.main()
