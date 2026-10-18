"""Independent synthetic ASML review; owner tests and saved builds excluded."""
from copy import deepcopy
import gzip
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_ndx_asml_incumbent_identity_20261002 as f
m=f.module
class Review(unittest.TestCase):
 def test_full_scope_separates_fund_and_issuer_and_no_adr(self):
  args=f.fixture();before=deepcopy(args);r=m.assemble(*args)
  self.assertEqual(args,before)
  self.assertEqual(r['security_id'],'security:0000937966:N07059210')
  self.assertEqual(r['nport_fact']['security_fields']['title'],'ASML Holding N.V., New York Shares')
  self.assertEqual(r['annual_registered_class'],'Ordinary Shares')
  self.assertNotEqual(r['issuer_cik'],r['nport_fact']['reporting_fund_cik'])
  self.assertIs(r['depositary_receipt_class_asserted'],False)
  self.assertIsNone(r['ads_conversion_ratio'])
  for flag in m.FALSE_FLAGS:self.assertIs(r[flag],False)
 def test_nested_cover_wrong_context_duplicate_and_segment(self):
  for attack in ('context','duplicate','segment'):
   args=f.fixture();raw=args[0]
   if attack=='context':raw=raw.replace(b'name="dei:TradingSymbol" contextRef="'+m.CONTEXT.encode()+b'"',b'name="dei:TradingSymbol" contextRef="other"')
   elif attack=='duplicate':raw+=b'<ix:nonNumeric name="dei:Security12bTitle" contextRef="other">Ordinary Shares</ix:nonNumeric>'
   else:raw=raw.replace(b'</xbrli:entity>',b'<xbrli:segment>OTHERCLASS</xbrli:segment></xbrli:entity>')
   f.resign_annual(args,raw)
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(*args)
 def test_resigned_nport_class_fund_isin_duplicate_and_decode(self):
  for old,new in [(b'New York Shares',b'American Depositary Shares'),(b'0001067839',b'0000937966'),(b'USN070592100',b'WRONG'),(b'</cusip>',b'</cusip><cusip>N07059210</cusip>')]:
   args=f.fixture();f.resign_xml(args,gzip.decompress(args[2]).replace(old,new))
   with self.subTest(old=old),self.assertRaises(ValueError):m.assemble(*args)
  args=f.fixture();args[-1]=m.digest(args[2])
  with self.assertRaisesRegex(ValueError,'decoded'):m.assemble(*args)
 def test_publish_preexisting_and_post_receipt_drift_fail_closed(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);output=root/'existing';output.mkdir()
   with patch.object(m,'OUTPUT',output),patch.object(m,'build') as build:
    with self.assertRaises(ValueError):m.publish()
    build.assert_not_called()
   output=root/'new';source=root/'source';source.write_text('sealed')
   result={'source_hashes':{str(source):m.digest(source.read_bytes())}};original=m.durable
   def drift(path,raw):
    original(path,raw)
    if path.name=='publication.json':source.write_text('drift')
   with patch.object(m,'OUTPUT',output),patch.object(m,'build',return_value=result),patch.object(m,'durable',side_effect=drift):
    with self.assertRaises(ValueError):m.publish()
    self.assertTrue((output/'failure.json').exists())
    with self.assertRaises(ValueError):m.publish()
if __name__=='__main__':unittest.main()
