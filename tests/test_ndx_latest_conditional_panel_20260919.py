import copy,json,unittest
import pandas as pd
from scripts import ndx_latest_conditional_panel_20260919 as m
from test_ndx_latest_conditional_panel_research import fixture as pure_fixture


class PanelRecipeTests(unittest.TestCase):
    def test_decoded_panel_digest_and_real_selected_mapping(self):
        panel=m.core.assemble_conditional_panel(**pure_fixture())
        decoded=m.typed_decode(json.loads(json.dumps(m.typed_encode(panel))))
        self.assertIsInstance(decoded['universe'].index,pd.RangeIndex)
        self.assertEqual(m.core.panel_digest(decoded),panel['panel_content_sha256'])
        selected=decoded['universe'].drop_duplicates('issuer_id')['security_id'].tolist()
        self.assertEqual(m.core.selected_mapping(decoded,selected),m.core.selected_mapping(panel,selected))

    def test_typed_datetime_float_and_integer_roundtrip(self):
        dates=pd.date_range('2026-01-01',periods=3)
        panel={name:pd.DataFrame({'A':[1.,2.,3.]},index=dates,dtype='float64') for name in m.FRAMES}
        panel['raw_volume']=pd.DataFrame({'A':[1,2,3]},index=dates,dtype='int64')
        panel['universe']=pd.DataFrame({'ticker':['A'],'security_id':['security:0000000001:000000000']})
        encoded=m.typed_encode(panel);restored=m.typed_decode(json.loads(json.dumps(encoded)))
        self.assertIsInstance(restored['returns'].index,pd.DatetimeIndex)
        self.assertEqual(str(restored['returns'].dtypes.iloc[0]),'float64')
        self.assertEqual(str(restored['raw_volume'].dtypes.iloc[0]),'int64')
        for defect in ('dtype','bool','index'):
            bad=copy.deepcopy(encoded)
            if defect=='dtype':bad['returns']['dtypes']=['int64']
            if defect=='bool':bad['raw_volume']['data'][0][0]=True
            if defect=='index':bad['returns']['index_kind']='fake'
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.typed_decode(bad)

    def test_actual_fact_anchor_is_not_joint_availability(self):
        calendar=['2026-03-18','2026-09-17']
        docs={k:json.loads((m.BASE/m.ANCHORS[k][0]).read_bytes()) for k in ('four','seven','two')}
        for key,ticker,expected in (('four','GOOG','2023-02-09'),('seven','FTNT','2022-06-22'),('two','NFLX','2025-11-04'),('two','PANW','2024-11-26')):
            fact=next(r for r in docs[key]['rows'] if r['ticker']==ticker)
            value=m.coordinate_from_fact(ticker,fact,key,calendar)
            self.assertEqual(value['dated_fact']['dated_as_of'],expected)
            extra=m.supplemental_provenance(fact,value,{})
            self.assertEqual(extra['complete_original_fact'],fact)
            self.assertFalse(extra['joint_historical_availability_inferred'])
            self.assertFalse(value['latest_interval_verified'])
            self.assertEqual(extra['date_role'],'SELECTED_DATED_FACT_ANCHOR_NOT_JOINT_AVAILABILITY')
            m.core.coordinate(value,{'ticker':ticker,'issuer_id':value['issuer_id']},calendar)


if __name__=='__main__':unittest.main()
