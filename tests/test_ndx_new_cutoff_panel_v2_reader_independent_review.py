"""Mock PCAR numbers, saved metadata only; never actual candidate audit."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_typed_panel_v2_independent_readback_20260924 as fixture

m=fixture.module


class IndependentIncrementReaderReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.Tests.setUpClass();cls.docs=fixture.Tests.documents;cls.numbers=fixture.Tests.numbers

    def candidate(self):
        with patch.object(m.codec,'channel_numbers',return_value=self.numbers):result=m.reconstruct_increment(self.docs)
        result['source_hashes']={};return result

    def test_rechecksummed_new_column_universe_and_99_gap_tampering_rejected(self):
        for attack in ('new_cell','old_class','gap'):
            candidate=self.candidate();panel=m.codec.decode_frames(candidate['panel'])
            if attack=='new_cell':panel['dollar_volume'].loc[panel['dollar_volume'].index[0],'PCAR']+=100.
            elif attack=='old_class':panel['universe'].loc[panel['universe'].ticker=='GOOG','security_class']='Class A'
            else:m.one(panel['observed_provenance_and_missing'],'CPRT')['blocking_reasons']=[]
            panel['panel_content_sha256']=m.codec.checksum(panel);candidate['panel']=m.codec.encode_frames(panel)
            with self.subTest(attack=attack),patch.object(m.codec,'channel_numbers',return_value=self.numbers),self.assertRaises(ValueError):
                m.verify_candidate(candidate,self.docs,{})

    def test_original_null_fact_and_late_memo_fail_before_numeric_call(self):
        for attack in ('pcar_null','crwd_date','other99'):
            docs=deepcopy(self.docs)
            if attack=='pcar_null':m.one(docs['wiring']['rows'],'PCAR')['complete_original_evidence'][0]['complete_original_fact']['risk_chain']='automotive'
            elif attack=='crwd_date':m.one(docs['wiring']['extended_provenance'],'CRWD')['complete_increment_evidence']['memo_publication_date']='2026-03-20'
            else:m.one(docs['wiring']['rows'],'AAPL')['gaps']=[]
            with self.subTest(attack=attack),patch.object(m.codec,'channel_numbers') as numbers:
                with self.assertRaises(ValueError):m.reconstruct_increment(docs)
                numbers.assert_not_called()

    def test_complete_increment_evidence_and_source_map_are_not_optional(self):
        for attack in ('increment','source'):
            candidate=self.candidate()
            if attack=='increment':candidate['incremental_evidence_and_projection'][0]['complete_extended_provenance']['complete_increment_evidence']={}
            else:candidate['source_hashes']={'missing':'0'*64}
            with self.subTest(attack=attack),patch.object(m.codec,'channel_numbers',return_value=self.numbers) as numbers:
                with self.assertRaises(ValueError):m.verify_candidate(candidate,self.docs,{})
                if attack=='source':numbers.assert_not_called()

    def test_orphan_namespace_fails_before_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'panel.json').write_text('{}');(root/'orphan').write_text('incomplete')
            with patch.object(m,'OUTPUT',root/'audit.json'),patch.object(m,'build') as build:
                with self.assertRaises(ValueError):m.publish()
                build.assert_not_called()


if __name__=='__main__':unittest.main()
