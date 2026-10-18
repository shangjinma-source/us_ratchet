import copy
import gzip
import json
import unittest
from pathlib import Path
from bs4 import BeautifulSoup
from scripts import ndx_latest_panel_independent_readback_20260919 as audit


class IndependentReadbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sources={}
        cls.value=audit.saved.read(dict(path=str(audit.BASE/'latest_conditional_panel_20260919_v1/panel.json'),sha256='06f917bcdf67a92bc0135ce7c1a5ac28e5ad8bac15823ed85968bfe744811ec0'),sources)
        cls.docs={k:audit.saved.read(audit.ref(k),sources) for k in audit.ANCHORS}
        cls.wrappers={e['ticker']:audit.saved.read(dict(path=e['path'],sha256=e['sha256']),sources) for e in cls.docs['index']['entries']}
        fact=next(r for r in cls.docs['seven']['rows'] if r['ticker']=='FTNT')
        path=Path(fact['evidence']['cover_path']);raw=path.read_bytes()
        assert audit.archive.drift.file_sha(path)==cls.value['historical_expected_source_hashes'][str(path.resolve())]
        soup=BeautifulSoup(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw,'html.parser')
        cls.periods={'FTNT':[dict(context=n.get('contextref'),original_text=n.get_text(' ',strip=True)) for n in soup.find_all() if n.get('name','').lower()=='dei:documentperiodenddate']}

    def inspect(self,value):return audit.inspect(value,self.docs,self.wrappers,self.periods)

    def test_actual_saved_panel_independent_reconstruction(self):
        result=self.inspect(self.value)
        self.assertEqual(result['returns_cells'],1134)
        self.assertTrue(result['rangeindex_and_panel_checksum_verified'])

    def test_each_numeric_frame_and_universe_tampering_rejected(self):
        for name in audit.FRAMES:
            value=copy.deepcopy(self.value)
            value['panel'][name]['data'][0][0]='forged' if name=='universe' else 123456789
            with self.subTest(name=name),self.assertRaises(ValueError):self.inspect(value)

    def test_index_gap_and_nested_date_provenance_tampering_rejected(self):
        for mutation in ('index','gap','date','privilege'):
            value=copy.deepcopy(self.value)
            if mutation=='index':value['panel']['universe']['index_kind']='Index'
            elif mutation=='gap':value['panel']['observed_provenance_and_missing'].pop()
            elif mutation=='date':value['supplemental_dated_and_risk_provenance']['FTNT']['joint_historical_availability_inferred']=True
            else:value['panel']['legal_training_input_admitted']=True
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):self.inspect(value)


if __name__=='__main__':unittest.main()
