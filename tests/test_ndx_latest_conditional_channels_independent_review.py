import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_latest_conditional_channels_20260919 as m


class RecoveryReview(unittest.TestCase):
    def test_resigned_boolean_type_changes_are_not_valid_recovery(self):
        for defect in ('plan','marker','result'):
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as d:
                folder=Path(d)/'tasks';folder.mkdir()
                tasks=[dict(ticker='T'+str(i),mode='BLOCKED',reason='fixture') for i in range(101)]
                plan=dict(tasks=tasks,historical_expected_source_hashes={},promotion_allowed=False)
                savedplan=copy.deepcopy(plan)
                if defect=='plan':savedplan['promotion_allowed']=0
                pref=m.exclusive_publish(Path(d)/'plan.json',savedplan)
                marker=dict(schema='LATEST_CHANNEL_ATTEMPT_V1',plan_sha256=pref['sha256'],task=tasks[0],attempt_count=1)
                if defect=='marker':marker['attempt_count']=True
                started=m.exclusive_publish(folder/'T0.started.json',marker)
                result=m.calculate(tasks[0],None,pref['sha256'])
                if defect=='result':result['promotion_allowed']=0
                saved=m.exclusive_publish(folder/'T0.json',result)
                entries=[dict(ticker='T0',**saved,started_sha256=started['sha256'])]
                index=m.index_value(entries,pref['sha256'],folder)
                ref=m.exclusive_publish(folder/'index_fixture.json',index)
                with patch.object(m,'load_prepared',return_value=(plan,{})),patch.object(m,'verify_sources',return_value={}):
                    with self.assertRaises(ValueError):
                        m.execute(pref['path'],pref['sha256'],folder,max_new=0,index_path=ref['path'],index_sha=ref['sha256'])


if __name__=='__main__':unittest.main()
