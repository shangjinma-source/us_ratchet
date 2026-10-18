from copy import deepcopy
import json
from types import SimpleNamespace
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import ndx_cash_neighbor_combined_independent_readback_20261008 as subject


class IndependentCombinedSourceReview(unittest.TestCase):
    def registration(self):
        return dict(schema='CASH_COMBINED_SOURCE_REGISTRATION_V1',
            domain=dict(original_task_count=301657,logical_shard_count=324,
                recovery_task_count=42301,recovery_segment_count=45,
                old_candidate_count=2648,selection_union_candidate_count=304305),
            references={},**subject.FLAGS)

    def test_resigned_external_scope_rejected_before_parent_consumption(self):
        for attack in ('subset','typed_count','authority','typed_flag'):
            document=self.registration()
            if attack=='subset':document['domain']['recovery_task_count']-=1
            elif attack=='typed_count':document['domain']['recovery_segment_count']=45.0
            elif attack=='authority':document['account_executed']=True
            else:document['evaluator_called']=0
            raw=subject.encode(document)
            helper=SimpleNamespace(fresh_oracle=lambda: None,decode=json.loads)
            with tempfile.TemporaryDirectory() as directory:
                registration=subject.ref(Path(directory)/'registration.json',subject.sha(raw))
                reads=[]
                def read(reference,**kwargs):
                    reads.append(reference)
                    if len(reads)>1:self.fail('Invalid registration consumed a parent')
                    return raw
                with patch.object(subject,'REGISTRATION_SHA',registration['sha256']),patch.object(subject,'PURE_SHA','a'*64),patch.object(subject,'OUTPUT',Path(directory)/'output'),patch.object(subject,'private',return_value=helper),patch.object(subject,'load_bytes',side_effect=read):
                    with self.subTest(attack=attack),self.assertRaises(ValueError):
                        subject.run(registration_reference=registration,execute=True)
                self.assertEqual(reads,[registration])

    def test_typed_source_digest_conflict_rejected_without_overwrite(self):
        source=str(subject.SOURCE);mapping={source:'a'*64};before=deepcopy(mapping)
        with self.assertRaises(ValueError):subject.merge_bindings(mapping,{source:'b'*64})
        self.assertEqual(mapping,before)
        with self.assertRaises(ValueError):subject.merge_bindings(mapping,{source:True})
        self.assertEqual(mapping,before)


if __name__=='__main__':unittest.main()
