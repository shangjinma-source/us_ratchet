"""Independent synthetic binding review; no actual build or owner test run."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_ndx_tsm_cash_inventory_binding_20261002 as f
m=f.m
class Review(unittest.TestCase):
 def test_all_pointers_resolve_exact_without_mutating_parent(self):
  args=f.fixture();before=deepcopy(args);result=m.assemble(*args)
  self.assertEqual(args,before)
  self.assertEqual(result['remaining_original_identity_gap_count'],155)
  for row in result['rows']:
   pointer=row['inventory_security_reference']['json_pointer'].split('/')
   original=args[0]['rows'][int(pointer[2])]['securities'][int(pointer[4])]
   self.assertEqual(original['security_id'],m.SID)
   self.assertEqual(row['original_security_row_sha256'],m.digest(m.encode(original)))
   self.assertEqual(row['original_gaps_preserved'],original['gaps'])
   for flag in m.FALSE:self.assertIs(row[flag],False)
  self.assertEqual(len({r['inventory_security_reference']['json_pointer'] for r in result['rows']}),31)
 def test_shift_coordinate_and_hidden_saved_coordinate_conflict(self):
  for attack in ('swap','extraissuer','gapclear','fork'):
   args=f.fixture();row=args[0]['rows'][1]
   if attack=='swap':args[0]['rows'][0]['securities'],row['securities']=row['securities'],args[0]['rows'][0]['securities']
   elif attack=='extraissuer':row['securities'][0]['saved_coordinates'].append({'value':{'ticker':'TSM','issuer_id':'issuer:other'}})
   elif attack=='gapclear':row['securities'][0]['gaps']=[];row['gaps'].pop(0)
   else:row['fork_executable']=1
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(*args)
 def test_receipt_path_source_map_and_sidecar_authority(self):
  for attack in ('path','sources','status','inline'):
   args=f.fixture()
   if attack=='path':args[4]['identity_reference']={'path':'other','sha256':'a'*64}
   elif attack=='sources':args[4]['source_hashes']={'wrong':'a'*64}
   elif attack=='status':args[1]['status']='FAILED'
   else:args[2]['inline_cik_field_verified']=True
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(*args)
 def test_failed_parent_namespace_rejected_before_assemble(self):
  with tempfile.TemporaryDirectory() as temp:
   base=Path(temp);a=base/'parent';a.mkdir();b=base/'side';b.mkdir()
   for name in ('inventory.json','publication.json','failure.json'):(a/name).write_text('{}')
   for name in ('identity.json','publication.json'):(b/name).write_text('{}')
   bound={'inventory':('parent/inventory.json','a'*64),'publication':('parent/publication.json','a'*64),'sidecar':('side/identity.json','a'*64),'sidecar_publication':('side/publication.json','a'*64)}
   with patch.object(m,'BASE',base),patch.object(m,'BOUND',bound),patch.object(m,'assemble') as assembly:
    with self.assertRaisesRegex(ValueError,'failed/orphan'):m.build()
    assembly.assert_not_called()
   with patch.object(m,'OUTPUT',a),patch.object(m,'build') as build:
    with self.assertRaises(ValueError):m.publish()
    build.assert_not_called()
if __name__=='__main__':unittest.main()
