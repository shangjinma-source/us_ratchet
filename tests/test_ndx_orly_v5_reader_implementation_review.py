"""Independent bounded reader attacks; no producer import or actual projection."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_typed_panel_v5_independent_readback_20260925 as m

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs={k:m.codec.loads(Path(m.ref(k)['path']).read_bytes()) for k in m.BOUND}
        cls.numbers=([.01]*126,[20.]*127,dict(volumes=[10000000]*63,dollars=[200000000.]*63,median=200000000.),None)
    def test_old_frame_and_fourth_sidecar_rechecksummed_attacks(self):
        for attack in ('cell','dtype','sidecar'):
            with patch.object(m.codec,'channel_numbers',return_value=self.numbers):value=m.reconstruct_increment(self.docs)
            value['source_hashes']={}
            if attack=='sidecar':value['v4_incremental_evidence_and_projection'][0]['complete_extended_provenance']={}
            else:
                panel=m.codec.decode_frames(value['panel']);ticker=next(t for t in panel['returns'].columns if t!='ORLY')
                if attack=='cell':panel['returns'].loc[panel['returns'].index[0],ticker]=.12345
                else:panel['raw_volume'][ticker]=panel['raw_volume'][ticker].astype('float64')
                panel['panel_content_sha256']=m.codec.checksum(panel);value['panel']=m.codec.encode_frames(panel)
            with self.subTest(attack=attack),patch.object(m.codec,'channel_numbers',return_value=self.numbers),self.assertRaises(ValueError):m.verify_candidate(value,self.docs,{})
    def test_source_map_conflict_rejected_before_numeric(self):
        with patch.object(m.codec,'channel_numbers') as calc,self.assertRaises(ValueError):m.verify_candidate({'source_hashes':{'extra':'a'}},self.docs,{})
        calc.assert_not_called()
        with self.assertRaises(ValueError):m.merged_sources({str(m.SOURCE):'0'*64})
    def test_original_dates_and_visual_identity_not_reinterpreted(self):
        for key,value in [('signature_date','2025-06-10'),('annual_fetched_at','2026-03-01'),('publication_date','2025-06-09')]:
            docs=deepcopy(self.docs);docs['wiring']['v5_extended_provenance'][0]['complete_increment_evidence'][key]=value
            with self.subTest(key=key),patch.object(m.codec,'channel_numbers') as calc,self.assertRaises(ValueError):m.reconstruct_increment(docs)
            calc.assert_not_called()

if __name__=='__main__':unittest.main()
