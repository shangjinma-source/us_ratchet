import copy
import unittest
from scripts import ndx_latest_conditional_channels_independent_audit_20260919 as m
from test_ndx_latest_conditional_channels_independent_audit_20260919 import BatchReaderTests


class AuditReaderReview(unittest.TestCase):
    def test_strict_full_order_and_marker_reference_shape(self):
        for defect in ('reorder','extraentry','entryfield','directory','boolplanned'):
            index,folder,tasks=BatchReaderTests().make_index()
            if defect=='reorder':index['entries'][0],index['entries'][1]=index['entries'][1],index['entries'][0]
            if defect=='extraentry':index['entries'].append(copy.deepcopy(index['entries'][0]))
            if defect=='entryfield':index['entries'][0]['status']='COMPLETE'
            if defect=='directory':index['output_directory']=str(folder.parent)
            if defect=='boolplanned':index['planned']=True
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.validate_index(index,'c'*64,folder,tasks)

    def test_numeric_wrapper_cannot_omit_output_change_input_or_upgrade_scope(self):
        task=dict(ticker='AMAT',mode='CALCULATE',reason=None,input_sha256='a'*64)
        base=dict(schema='LATEST_CONDITIONAL_CHANNEL_TASK_V1',plan_sha256='p',task=task,status='CONDITIONAL_NUMERIC_RESULT',result={},**dict.fromkeys(m.recipe.FALSE,False))
        m.validate_wrapper(base,task,'p')
        for defect in ('null','task','plan','field','scope'):
            value=copy.deepcopy(base)
            if defect=='null':value['result']=None
            if defect=='task':value['task']['input_sha256']='b'*64
            if defect=='plan':value['plan_sha256']='other'
            if defect=='field':value['execution_performed']=True
            if defect=='scope':value['legal_training_input_admitted']=0
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.validate_wrapper(value,task,'p')


if __name__=='__main__':unittest.main()
