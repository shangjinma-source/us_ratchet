import unittest,hashlib
from scripts.research.propose_news_two_mechanisms_v1 import validate,source_records

def source(i,t):return {'id':i,'text':t,'text_sha256':hashlib.sha256(t.encode()).hexdigest()}
def answer():
 common={'reason':'research','counterevidence':[],'uncertainty':[],'evidence':[{'source_id':'current','quote':'current facts'}]}
 return {'source_id':'current','shared_facts':[{'fact':'prior','exact_quote':'prior facts','source_id':'prior','uncertainty':''}], 'A_direct':dict(common,action='KEEP',buy_fraction='1',holding_fraction='1'),'B_signal':dict(common,direction='NEUTRAL',materiality='UNCERTAIN'),'limitations':[]}
class MultiSourceTests(unittest.TestCase):
 def test_multi(self):validate(answer(),{'id':'current','sources':[source('prior','prior facts'),source('current','current facts')]})
 def test_wrong_source_quote_rejected(self):
  a=answer();a['shared_facts'][0]['source_id']='current'
  with self.assertRaisesRegex(ValueError,'QUOTE_NOT_IN_SOURCE'):validate(a,{'id':'current','sources':[source('prior','prior facts'),source('current','current facts')]})
 def test_single_preserved(self):
  a=answer();a['shared_facts']=[];validate(a,source('current','current facts'))
 def test_hash_rejected(self):
  s=source('current','current facts');s['text']='changed'
  with self.assertRaisesRegex(ValueError,'TEXT_HASH_MISMATCH'):source_records(s)
 def test_duplicate_rejected(self):
  with self.assertRaisesRegex(ValueError,'DUPLICATE_SOURCE_ID'):source_records({'id':'current','sources':[source('current','a'),source('current','b')]})
if __name__=='__main__':unittest.main()
