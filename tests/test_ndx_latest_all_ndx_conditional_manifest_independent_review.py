"""Independent scope/denominator attacks; never build or publish actual manifest."""
import copy
import unittest
from unittest.mock import patch
from scripts import ndx_latest_all_ndx_conditional_manifest_20260919 as m
from test_ndx_latest_all_ndx_conditional_manifest_20260919 import fixture


class ManifestReview(unittest.TestCase):
    def test_verified_output_cannot_invent_sid_remove_gap_or_drop_split(self):
        docs=fixture()
        for defect in ('sid','class','gap','event','issuer','admission','count'):
            result=m.assemble(**copy.deepcopy(docs))
            rows={r['ticker']:r for r in result['rows']}
            if defect=='sid':rows['AMAT']['security_id']='security:0000006951:038222105'
            if defect=='class':rows['GOOG']['share_class']='Class A'
            if defect=='gap':rows['HONA']['history_failures']=[]
            if defect=='event':rows['MNST']['raw_returned_split_events']=[]
            if defect=='issuer':result['issuer_to_observed_tickers']['issuer:0001652044']=['GOOG']
            if defect=='admission':result['legal_training_input_admitted']=True
            if defect=='count':result['counts']['observed_issuers']=101
            with self.subTest(defect=defect),patch.object(m,'load_inputs',return_value=(docs,{})),self.assertRaises(ValueError):
                m.verify(result)

    def test_same_position_issuer_class_and_complete_reference_required(self):
        for defect in ('wrongexchange','swapticker','compress','duplicate'):
            docs=fixture()
            row=next(r for r in docs['issuers']['rows'] if r['ticker']=='GOOG')
            if defect=='wrongexchange':row['matched_candidate']['reported_exchanges'][row['reported_ticker_exchange_position']]='NYSE'
            if defect=='swapticker':row['reported_ticker_exchange_position']=0
            if defect=='compress':docs['readiness']['observed_reference_calendar'].pop(-20)
            if defect=='duplicate':docs['observation']['rows'][-1]=copy.deepcopy(docs['observation']['rows'][0])
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.assemble(**docs)


if __name__=='__main__':unittest.main()
