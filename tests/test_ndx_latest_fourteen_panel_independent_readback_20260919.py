import copy
import json
import unittest
from scripts import ndx_latest_fourteen_panel_independent_readback_20260919 as m


class FourteenReadbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sources={};cls.value=m.read(m.PANEL,sources);cls.old=m.read(m.OLD,sources);cls.facts=m.read(m.FIVE,sources)
        cls.proposals=m.read(m.prior.ref('fifteen'),sources);index=m.read(m.prior.ref('index'),sources);plan=m.read(m.prior.ref('plan'),sources)
        cls.wrappers={task['ticker']:m.read(dict(path=entry['path'],sha256=entry['sha256']),sources) for entry,task in zip(index['entries'],plan['tasks']) if task['ticker'] in m.ADDED}

    def inspect(self,value):return m.inspect(value,self.old,self.facts,self.proposals,self.wrappers)

    def test_real_saved_fourteen_reconstruction_without_producer(self):
        self.assertEqual(self.inspect(self.value),m.DETAILS)

    def test_old_and_new_cells_and_all_provenance_are_bound(self):
        for name in ('returns','nominal_close','raw_volume','dollar_volume'):
            for ticker in ('AMAT','LRCX'):
                bad=copy.deepcopy(self.value);frame=bad['panel'][name];frame['data'][0][frame['columns'].index(ticker)]+=1
                with self.subTest(name=name,ticker=ticker),self.assertRaises(ValueError):self.inspect(bad)
        bad=copy.deepcopy(self.value);bad['panel']['observed_provenance_and_missing'][-1]['source_assertions_authenticated']=True
        with self.assertRaises(ValueError):self.inspect(bad)

    def test_lrcx_dates_scope_and_index_types_not_upgraded(self):
        for kind in ('date','class','scope','range'):
            bad=copy.deepcopy(self.value)
            if kind=='date':bad['supplemental_dated_and_risk_provenance']['LRCX']['selected_anchor_kind']='PUBLICATION'
            elif kind=='class':bad['panel']['universe']['data'][0][4]='Class B'
            elif kind=='range':bad['panel']['universe']['index_kind']='Index'
            else:bad['promotion_allowed']=True
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.inspect(bad)

    def test_report_boolean_count_and_scope_rejected(self):
        value=dict(schema='LATEST_FOURTEEN_CONDITIONAL_PANEL_INDEPENDENT_READBACK_V1',panel_reference=m.PANEL,old9_reference=m.OLD,old9_audit_reference=m.AUDIT,five_identity_reference=m.FIVE,details=dict(m.DETAILS),historical_expected_source_hashes={},archive_resolution={},**dict.fromkeys(m.FALSE,False))
        m.validate_report(value)
        for kind in ('count','scope'):
            bad=copy.deepcopy(value)
            if kind=='count':bad['details']['added_securities']=True
            else:bad['producer_assemble_called']=True
            with self.assertRaises(ValueError):m.validate_report(bad)


if __name__=='__main__':unittest.main()
