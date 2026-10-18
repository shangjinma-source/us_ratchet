import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_september_cutoff_snapshot_independent_readback_20260923 as m
from test_ndx_september_cutoff_snapshot_independent_readback_20260923 import fixture


class Review(unittest.TestCase):
    def test_other_month_binding_and_false_success_rejected_without_global_patch(self):
        original=m.may.QUEUE
        with patch.object(m,'PLANNED',104),patch.object(m,'QUEUE_SHA','1'*64):
            q,i,v,a=fixture()
            m.validate_task(v,a,q,i,m.validate_index(i,q))
            bad=copy.deepcopy(i);bad['queue']={'path':str(m.may.QUEUE),'sha256':m.may.QUEUE_SHA}
            with self.assertRaises(ValueError):m.validate_index(bad,q)
            v['result']['refit']=None
            with self.assertRaises(ValueError):m.validate_task(v,a,q,i,m.validate_index(i,q))
            q,i,v,a=fixture();i['completed'][0]['job_id']='unknown'
            with self.assertRaises(ValueError):m.validate_index(i,q)
        self.assertEqual(m.may.QUEUE,original)

    def test_publication_rebuild_rejects_relabelled_result_or_removed_source(self):
        good={'schema':m.SCHEMA,'index':{'path':'external','sha256':'a'*64},'completed':1,'details':[{'job_id':'x','typed_decimal':{'fit_row_count':126}}],
              'historical_expected_source_hashes':{'required.py':'b'*64},'promotion_allowed':False}
        with tempfile.TemporaryDirectory() as folder:
            for defect in ('completed','source','detail','permission'):
                value=copy.deepcopy(good)
                if defect=='completed':value['completed']=True
                elif defect=='source':value['historical_expected_source_hashes']={}
                elif defect=='detail':value['details'][0]['typed_decimal']['fit_row_count']=125
                else:value['promotion_allowed']=True
                with self.subTest(defect=defect),patch.object(m,'build',return_value=good),patch.object(m,'publish') as publish:
                    with self.assertRaises(ValueError):m.publish_verified(Path(folder)/'audit.json',value)
                    publish.assert_not_called()


if __name__=='__main__':unittest.main()
