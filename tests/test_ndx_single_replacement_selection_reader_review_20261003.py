from copy import deepcopy
from decimal import localcontext, Inexact
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_single_replacement_selection_independent_readback_20261003 as m
from scripts import ndx_single_replacement_selection_20261003 as p
from test_ndx_single_replacement_selection_publisher_20261003 import physical

class Tests(unittest.TestCase):
 def test_independent_positive_ranking_typed_and_subdecimal_corruption(self):
  from test_ndx_single_replacement_selection_research import fixture
  from backtest import ndx_single_replacement_selection_research as producer
  a=fixture();saved=producer.select_complete_single_replacements(**a)
  c=dict(prepared=a['prepared'],audit=a['readback'],refs=dict(preparation=a['preparation_reference'],execution_audit=a['readback_reference']))
  with patch.object(p,'TOTAL',560),patch.object(p,'stream_records',side_effect=lambda unused:iter(a['records'])),patch.object(producer,'select_complete_single_replacements',side_effect=AssertionError('No selector')):
   with localcontext() as ctx:
    ctx.prec=1;ctx.traps[Inexact]=True
    counts=m.inspect_selection(c,saved)
   self.assertEqual(counts['selected_case_count'],40)
   for mode in ('tiny','pointer','false'):
    bad=deepcopy(saved);row=bad['document']['rows'][0]
    if mode=='tiny':row['selected']['evaluation']['total_fee_usd']='1/100000000000000000000000000000000000000000000000000000000000000000000000000000001'
    elif mode=='pointer':row['selected']['source_reference']['journal_reference']['path']='E:/foreign/journal.jsonl'
    else:bad['document']['execution_authorized']=0
    bad['content_sha256']=p.sha(p.enc(bad['document']))
    with self.subTest(mode=mode),self.assertRaises(ValueError):m.inspect_selection(c,bad)
 def test_late_nested_parent_failure_never_gets_success_or_retry(self):
  with tempfile.TemporaryDirectory() as t,physical(Path(t)) as rr:
   refs=p.run(registration_reference=rr,execute=True);original=m.save
   def changed(name,value):
    result=original(name,value)
    if name=='independent_readback.json':
     shard=next(p.EXECUTION.glob('shard-*'));(shard/'failure.json').write_bytes(b'{}')
    return result
   with patch.object(m,'OUTPUT',Path(t)/'reader'),patch.object(m,'save',changed):
    with self.assertRaises(ValueError):m.readback(registration_reference=rr,selection_reference=refs['selection'],publication_reference=refs['publication'],execute=True)
    self.assertTrue((m.OUTPUT/'failure.json').exists())
    with self.assertRaises(ValueError):m.readback(registration_reference=rr,selection_reference=refs['selection'],publication_reference=refs['publication'],execute=True)

if __name__=='__main__':unittest.main()
