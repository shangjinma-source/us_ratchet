from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import date,timedelta
from hashlib import sha256
from copy import deepcopy
from unittest.mock import patch
import json
import unittest
from scripts.preflight_saved_integer_box_inputs import preflight,digest


def fixture(folder):
    root=Path(folder);(root/'raw.bin').write_bytes(b'historical')
    dates=[(date(2025,1,1)+timedelta(days=i)).isoformat() for i in range(253)]
    args=dict(prices={'A':'2','B':'3'},metadata={s:dict(ticker=s,issuer_id=s) for s in 'AB'},entered_cash='10',fee_bps='0',minimum_cash_buffer='0',training_scenarios=[{'A':'1','B':'1'} for _ in range(12)],scenario_dates=dates[21::21],decision_date=dates[-1],max_objective_evaluations=8192,fixed_seed='saved')
    old={k:args[k] for k in ('entered_cash','fee_bps','minimum_cash_buffer','decision_date','scenario_dates')}
    candidate=dict(quantities={'A':2},actual_k=1,notional='4',residual_cash='6',training_gross_growth_product='1')
    rows=[dict(status='DRAFT_CONDITIONAL_INPUT_COMPUTED',security_id=s,ticker=s,issuer_id=s,identity_binding=dict(security_id=s,ticker=s,valid_from=dates[0],valid_through=dates[-1]),training_source='raw.bin',training_close=[args['prices'][s]]*253,decision_cost=args['prices'][s]) for s in 'AB']
    prepared=dict(windows=[dict(decision_date=dates[-1],training_dates=dates,candidates=rows,member_denominator=2,search_arguments=args)],source_hashes={'raw.bin':sha256((root/'raw.bin').read_bytes()).hexdigest()})
    saved=dict(status='SAVED_FRONTIER_PLUS_CONTINUOUS_CANDIDATES',inherited_saved_result=old,selected=candidate,binding=dict(search_arguments_sha256=digest(args),saved_result_sha256=digest(old)))
    def write():
        (root/'prepared.json').write_text(json.dumps(prepared));(root/'saved.json').write_text(json.dumps(saved))
        return dict(root=root,prepared_path='prepared.json',prepared_sha256=sha256((root/'prepared.json').read_bytes()).hexdigest(),result_path='saved.json',result_sha256=sha256((root/'saved.json').read_bytes()).hexdigest(),decision_date=dates[-1])
    return prepared,saved,write


class AdapterTests(unittest.TestCase):
    def test_complete_domain_no_search_no_writes(self):
        with TemporaryDirectory() as folder:
            p,s,write=fixture(folder);args=write();before={f.name:f.read_bytes() for f in Path(folder).iterdir()}
            with patch('backtest.quantity_integer_box_certificate_prototype.solve',side_effect=AssertionError('no search')):result=preflight(**args)
            self.assertEqual(result['eligible_sid_count'],2);self.assertEqual(result['affordable_k'],[0,1,2]);self.assertEqual(result['root_integer_box_points'],'24')
            self.assertEqual(result['search_calls'],0);self.assertEqual(before,{f.name:f.read_bytes() for f in Path(folder).iterdir()})

    def test_omitted_identity_scenario_and_source_drift(self):
        for kind in ('omitted','identity','scenario','raw','cash'):
            with self.subTest(kind=kind),TemporaryDirectory() as folder:
                p,s,write=fixture(folder)
                if kind=='omitted':p['windows'][0]['candidates'].pop()
                elif kind=='identity':p['windows'][0]['candidates'][0]['issuer_id']='current-replacement'
                elif kind=='scenario':p['windows'][0]['candidates'][0]['training_close'][21]='4'
                elif kind=='cash':s['inherited_saved_result']['entered_cash']='11'
                args=write()
                if kind=='raw':(Path(folder)/'raw.bin').write_bytes(b'drift')
                with self.assertRaises(ValueError):preflight(**args)

if __name__=='__main__':unittest.main()
