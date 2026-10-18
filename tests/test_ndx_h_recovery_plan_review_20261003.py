import unittest
from copy import deepcopy
from test_ndx_h_failed_export_recovery_plan_research import fixture
from backtest import ndx_h_failed_export_recovery_plan_research as m

class Review(unittest.TestCase):
 def test_windows_aliases_and_success_parent_rejected(self):
  for name in ('PUBLICATION.JSON','Export_Manifest.json','/foreign','a//b','a/stream:ads','a/../b'):
   a=fixture();a['parent_inventory'].append(dict(path=name,sha256='a'*64,byte_count=1))
   with self.subTest(name=name),self.assertRaises(ValueError):m.plan_failed_export_recovery(**a)

 def test_required_parent_sources_previews_and_typed_flags(self):
  for name in ('sources/publication.json','sources/audit.json','sources/shared.json','sources/classification.json'):
   a=fixture();a['parent_inventory']=[r for r in a['parent_inventory'] if r['path']!=name]
   with self.subTest(name=name),self.assertRaises(ValueError):m.plan_failed_export_recovery(**a)
  a=fixture();a['attempts'][0]['pending']['previews']=[]
  with self.assertRaises(ValueError):m.plan_failed_export_recovery(**a)
  for obj,key in [('failure','retry_allowed'),('started','fit_performed')]:
   a=fixture();a[obj][key]=0
   with self.assertRaises(ValueError):m.plan_failed_export_recovery(**a)

 def test_complete_plan_is_not_byte_or_dispatch_authority(self):
  a=fixture();before=deepcopy(a);o=m.plan_failed_export_recovery(**a)
  self.assertEqual(a,before);self.assertEqual(len(o['navigation_links']),1632)
  self.assertEqual([p['action'] for p in o['packages']],['COPY_ORIGINAL_BYTES_NO_SDK_EXPORT','REBUILD_SINGLETON_WITH_REGISTERED_B5_ONLY_DELTA'])
  for key in ('machine_eof_verified','source_bytes_authenticated','recovery_dispatch_authorized','chart_and_cell_data_verified',*m.FLAGS):self.assertIs(o[key],False)

if __name__=='__main__':unittest.main()
