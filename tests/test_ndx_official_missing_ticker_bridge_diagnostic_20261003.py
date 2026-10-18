import copy,json,unittest
from scripts import ndx_official_missing_ticker_bridge_diagnostic_20261003 as m

def fixture():
 rows=[{'@type':'ListItem','position':i,'name':f'Name {i}'}for i in range(1,102)]
 for i,n in m.NAMES:rows[i-1]['name']=n
 companies=b'<script>'+json.dumps({'@graph':[{'@type':'ItemList','itemListElement':rows}]}).encode()+b'</script>'
 fields={'Company/Issue:':'Electronic Arts Inc. Common Stock','CUSIP#:':'285512109','Symbol:':'EA','Last Trading Date:':'August 4, 2026','Marketplace Effective Date for Suspension:':'August 5, 2026'}
 ea=('Friday, July 31, 2026 UPDATED: Merger closed<table>'+''.join(f'<tr><th><strong>{k}</strong></th><td>{v}</td></tr>'for k,v in fields.items())+'</table>').encode()
 zs='Zscaler, Inc.\u00a0(Nasdaq: ZS)<div class="field__item">May 26, 2026</div>'.encode()
 raws={'ea_name_symbol':b'403 EA false bridge','mu_name_symbol':b'403 Micron Technology Inc. Nasdaq MU','zs_name_symbol':zs,'ea_suspension':ea}
 receipts={n:dict(schema='OFFICIAL_MISSING_TICKER_BRIDGE_RECEIPT_V1',name=n,request=dict(method='GET',url=u),response_reference=m.ref(n+'.bin',raws[n]),transport_metadata=dict(http_status=200 if n in ('zs_name_symbol','ea_suspension')else 403,headers={}),body_complete=True,error=None,started_at_utc='2026-10-03T00:00:00Z',completed_at_utc='2026-10-03T00:00:01Z',**dict.fromkeys(m.PARENT_FALSE,False))for n,u in m.PAGES}
 return companies,raws,receipts
class Tests(unittest.TestCase):
 def test_three_original_rows_two_bridges_and_dated_conflict(self):
  a=fixture();d=m.diagnose(*a);self.assertEqual([r['ticker']for r in d['rows']],['EA',None,'ZS'])
  e=d['rows'][0]['evidence'][0];self.assertEqual((e['last_trading_date'],e['suspension_effective_date']),('2026-08-04','2026-08-05'));self.assertIsNone(e['available_at']);self.assertEqual(d['observed_name_symbol_count'],2)
  for row in d['rows']:self.assertTrue(all(row[k]is False for k in m.FLAGS))
  for x in e['fields'].values():
   l=x['location'];self.assertEqual(m.sha(a[1]['ea_suspension'][l['byte_start']:l['byte_stop']]),l['fragment_sha256'])
 def test_role_flags_source_and_duplicate_evidence_attacks(self):
  for attack in ('raw','role','false','duplicate','position'):
   a=list(fixture())
   if attack=='raw':a[1]['ea_suspension']+=b'tamper'
   elif attack=='role':a[2]['zs_name_symbol']['name']='mu_name_symbol'
   elif attack=='false':a[2]['ea_suspension']['current_listing_verified']=0
   elif attack=='position':a[0]=a[0].replace(b'ELECTRONIC ARTS INC',b'OTHER')
   else:
    a[1]['ea_suspension']+=b'<tr><th>Symbol:</th><td>EA</td></tr>';a[2]['ea_suspension']['response_reference']=m.ref('ea_suspension.bin',a[1]['ea_suspension'])
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.diagnose(*a)
 def test_403_and_incomplete_do_not_make_bridge(self):
  a=fixture();a[2]['zs_name_symbol']['body_complete']=False;d=m.diagnose(*a);self.assertIsNone(d['rows'][2]['ticker']);self.assertIsNone(d['rows'][1]['ticker'])
if __name__=='__main__':unittest.main()

