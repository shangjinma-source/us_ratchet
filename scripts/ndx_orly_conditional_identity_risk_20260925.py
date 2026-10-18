"""Saved ORLY evidence linked under explicit retrospective research assumptions."""
import argparse
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
try:
 import pypdf
except ModuleNotFoundError:
 sys.path.append(str(Path('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/Lib/site-packages')))
 import pypdf
import bs4
from bs4 import BeautifulSoup
import yaml
SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];BASE=ROOT/'data/cache/research'
OUTPUT=BASE/'orly_conditional_identity_risk_20260925_v1/declaration.json'
BOUND={
 'form_pdf':(ROOT/'data/cache/research/orly_identity_evidence_capture_20260925_v1/issuer_form_8937.response.bin','245ba08ebd6dbfb875dbf957dbee9cdd2f26f218a11bc441a299b7009596e9d0'),
 'page1':(ROOT/'data/cache/research/orly_identity_evidence_capture_20260925_v1/issuer_form_8937-page-1.png','7fdb95c9344023614759678586418e61680e8a6e89a01cc8db37b9f3672a9745'),
 'page2':(ROOT/'data/cache/research/orly_identity_evidence_capture_20260925_v1/issuer_form_8937-page-2.png','49d756412dfdff46195442046347c3215bd8203230d1010c6dfdc0b8373e573b'),
 'index':(ROOT/'data/cache/research/orly_identity_evidence_capture_20260925_v1/index.json','84395c8b4a1e5d6db11ba957e12d5d39a07b512dfa92ee4b592b82e84bf40a2d'),
 'capture_started':(ROOT/'data/cache/research/orly_identity_evidence_capture_20260925_v1/started.json','84e5ce1b1a3a70cb4ebe6c06bfa447a227ee8b731a7f2e81e9905b98ed572d79'),
 'form_started':(ROOT/'data/cache/research/orly_identity_evidence_capture_20260925_v1/issuer_form_8937.started.json','193cfed88562c0130f4e572edcda48e33db00b544757135a3dbcb371e38b6e81'),
 'form_receipt':(ROOT/'data/cache/research/orly_identity_evidence_capture_20260925_v1/issuer_form_8937.receipt.json','3e5dd19960ddc27ab5c9ac6e6a10a3da1e477021819d721b3a42ccc84ff5cd10'),
 'occ_started':(ROOT/'data/cache/research/orly_identity_evidence_capture_20260925_v1/occ_56584.started.json','2a432deb21e65e9bc7f651e308e887d64e89b9fb1ac98234ceb30a648d59116c'),
 'occ_receipt':(ROOT/'data/cache/research/orly_identity_evidence_capture_20260925_v1/occ_56584.receipt.json','65291e093037ef710bc484ad035c4cec242ee81b3369778f3ee54b93d9f8a04a'),
 'occ_failed_body':(ROOT/'data/cache/research/orly_identity_evidence_capture_20260925_v1/occ_56584.response.bin','a47d637f21f97e8e25c01527751d304db02e9e112d7abb7a339f749bb7bc5855'),
 'faq':(ROOT/'data/cache/research/remaining_standard_split_evidence_20260912_v1/orly.response.bin','dfa5cb9358ca845a9357fd19c157fc61db5b830cdab050bb0876e17eef4e3820'),
 'registry':(ROOT/'data/cache/research/standard_split_exact_gap_20260919_v1/registry_readback.json','61c1a7a07f1a3ad65d3fffac43e8a8b4494c58c67192d93808333073f711c32e'),
 'annual':(ROOT/'data/cache/candidate_pools/ndx_taxonomy_v2/current_review_20260713/raw_sec/issuer_0000898173/000089817326000009/orly-20251231x10k.htm','fd313323241a318af01c0142feb603444f1bb9f8dbf1ab7bddb1cbc351045994'),
 'config':(ROOT/'config/ndx_v11_current_taxonomy_review_decisions.yaml','392aea1025557a9a67bafcdc4197258970228736a7bb7b300d4bb23d7ce30c51'),
 'snapshot':(ROOT/'data/cache/candidate_pools/ndx_taxonomy_v2/current_review_20260713/reviewed/review_decisions_snapshot.yaml','2313e9f7a2b3cad2b22dca7c7f2431dd57e74a5a4cf4c3bbca2c9c8eafa87f81'),
 'taxonomy':(ROOT/'config/candidate_taxonomy_v2.yaml','3f1457a3d2de4b41f8e885ff4efb6e0f4191cf1b4463f979fb05b83af7cc1cc6'),
 'root_visual_review':(ROOT/'DYNAMIC_ORLY_FORM8937_ROOT_VISUAL_READBACK_20260925.md','fcabc6524d3b361fab4ee772760d93099ce09c2aa0fbf3d9a3fea689fce05bf5'),
 'source_lead':(ROOT/'DYNAMIC_ORLY_SAVED_SOURCE_LEAD_20260925.md','6c3edc398f162cb33c87be1e829831f478fab5f0e844f2b3b0dbbe1254b32d00'),
 'capture_readback':(ROOT/'DYNAMIC_ORLY_NEW_IDENTITY_SOURCE_CAPTURE_READBACK_20260925.md','b4a80c7da39ce89478aaf29b83b48851cd3f71005a86a498b61afa287fb37c08'),
 'manifest':(ROOT/'data/cache/candidate_pools/ndx_taxonomy_v2/current_review_20260713/raw_sec/issuer_0000898173/000089817326000009/orly-20251231x10k.htm.manifest.json','602b1203d71a0f6df3605c1c008a32c84021d25871dd28430b18ecbd341b86d3'),
}
def sha(blob):return hashlib.sha256(blob).hexdigest()
LOADED={str(p):sha(p.read_bytes()) for p in [SOURCE,*Path(pypdf.__file__).parent.rglob('*.py'),*Path(bs4.__file__).parent.rglob('*.py'),*Path(yaml.__file__).parent.rglob('*.py')]}
FALSE=('point_in_time_verified','identity_interval_verified','risk_interval_verified','provider_binding_verified','complete_corporate_actions_verified',
 'legal_training_input_admitted','promotion_allowed','execution_authorized','fit_performed','http_performed','prices_recomputed','old_facts_modified','panel_modified',
 'direct_single_document_cusip_cik_proof','classification_uniquely_proven','sec_filing_timestamp_independently_verified','early_window_review_availability_verified',
 'early_window_local_evidence_available','runtime_binary_closure_verified','full_transitive_source_closure_reverified','option_contract_terms_used_as_equity_identity')
TITLE='Common Stock'
URL='https://www.sec.gov/Archives/edgar/data/898173/000089817326000009/orly-20251231x10k.htm'
FORM_URL='https://corporate.oreillyauto.com/wp-content/uploads/2025/07/2025-IRS-Form-8937.pdf'
OCC_URL='https://infomemo.theocc.com/infomemos?number=56584'
CONTEXT='Duration_1_1_2025_To_12_31_2025_p_pPgbBgVk29y8ot1Bauiw'
def require(ok,message):
 if not ok:raise ValueError(message)
def ref(role):return dict(path=str(BOUND[role][0]),sha256=BOUND[role][1])
def one(rows,key,value):
 matches=[r for r in rows if r.get(key)==value];require(len(matches)==1,'Unique '+key);return matches[0]



def cover_facts(raw):
 soup=BeautifulSoup(raw.decode('utf-8'),'html.parser')
 def local(tag,name):return tag.name and tag.name.split(':')[-1].lower()==name
 contexts=soup.find_all(lambda t:local(t,'context') and t.get('id')==CONTEXT)
 require(len(contexts)==1,'Unique saved annual context');context=contexts[0]
 ids=context.find_all(lambda t:local(t,'identifier'))
 require(len(ids)==1 and ids[0].get('scheme')=='http://www.sec.gov/CIK' and ids[0].get_text(strip=True)=='0000898173','Annual context CIK')
 dates={k:[t.get_text(strip=True) for t in context.find_all(lambda t:local(t,k))] for k in ('startdate','enddate')}
 require(dates==dict(startdate=['2025-01-01'],enddate=['2025-12-31']),'Annual context interval')
 fields=[]
 for name,value in [('dei:EntityCentralIndexKey','0000898173'),('dei:Security12bTitle',TITLE),('dei:TradingSymbol','ORLY')]:
  tags=soup.find_all(lambda t:local(t,'nonnumeric') and t.get('name','').lower()==name.lower() and t.get('contextref')==CONTEXT)
  require(len(tags)==1 and ' '.join(' '.join(tags[0].stripped_strings).split())==value,'Same-context common stock cover')
  fields.append(dict(name=name,context=CONTEXT,value=value))
 text=' '.join(soup.stripped_strings);phrase='specialty retailers of automotive aftermarket parts'
 offsets=[m.start() for m in re.finditer(re.escape(phrase),text)]
 require(offsets,'Exact saved business phrase required')
 return dict(context_id=CONTEXT,entity_cik='0000898173',period=dates,fields=fields,business_phrase=phrase,
  business_phrase_offsets=offsets,occurrence_count=len(offsets),text_normalization='BeautifulSoup_html.parser_stripped_strings_single_space_join',normalized_text_sha256=sha(text.encode()))


def capture_facts(docs,blobs):
 from datetime import datetime,timezone
 index=docs['index'];require(index['schema']=='ORLY_IDENTITY_EVIDENCE_CAPTURE_INDEX_V1' and type(index['completed_attempt_count']) is int and index['completed_attempt_count']==2,'Two attempts retained')
 require(index['receipts']==[docs['occ_receipt'],docs['form_receipt']] and index['retry_allowed'] is False and index['point_in_time_verified'] is False,'Complete capture index')
 started=docs['capture_started'];require(started['schema']=='ORLY_IDENTITY_EVIDENCE_CAPTURE_STARTED_V1' and started['single_attempt_per_url'] is True and
  started['urls']==[dict(key='occ_56584',url=OCC_URL),dict(key='issuer_form_8937',url=FORM_URL)],'Original two URL scope')
 def utc(value):
  d=datetime.fromisoformat(value);require(d.tzinfo is not None and d.utcoffset()==timezone.utc.utcoffset(d),'Aware UTC receipt');return d
 for role,key,url,status,content_type,body in [('occ','occ_56584',OCC_URL,403,'text/html; charset=UTF-8','occ_failed_body'),('form','issuer_form_8937',FORM_URL,200,'application/pdf','form_pdf')]:
  r=docs[role+'_receipt'];s=docs[role+'_started']
  require(r['schema']=='ORLY_IDENTITY_EVIDENCE_HTTP_RECEIPT_V1' and s['schema']=='ORLY_IDENTITY_EVIDENCE_HTTP_STARTED_V1' and r['key']==s['key']==key,'Exact receipt/started schema')
  require(r['original_url']==r['final_url']==s['original_url']==url and s['method']=='GET' and type(r['http_status']) is int and r['http_status']==status and r['content_type']==content_type,'Exact original result status')
  for item in (r,s):
   require(type(item['attempt']) is int and item['attempt']==1 and all(item[k] is False for k in ('retry_allowed','cookies_saved','credentials_supplied')),'Single attempt without cookie credentials')
  require(r['point_in_time_verified'] is False and s['started_at_utc']==r['started_at_utc'] and utc(started['started_at_utc'])<=utc(r['started_at_utc'])<=utc(r['received_at_utc']),'Receipt clock ordering')
  require(r['raw_reference']==dict(ref(body),byte_count=len(blobs[body])) and sha(blobs[body])==BOUND[body][1],'Raw bytes receipt linkage')
 require(docs['occ_receipt']['error']['type']=='HTTPError' and docs['form_receipt']['error'] is None and
  blobs['occ_failed_body'].lstrip().startswith(b'<!DOCTYPE html>') and blobs['form_pdf'].startswith(b'%PDF-'),'Failure HTML is not successful memo')
 require(docs['form_receipt']['received_at_utc']=='2026-09-24T17:37:33.511356+00:00','Preserve actual late receipt')
 return dict(capture_index=deepcopy(index),capture_started=deepcopy(started),form_started=deepcopy(docs['form_started']),
  form_receipt=deepcopy(docs['form_receipt']),occ_started=deepcopy(docs['occ_started']),occ_receipt=deepcopy(docs['occ_receipt']),
  occ_local_pdf_available=False,occ_failure_is_identity_source=False,occ_failed_body_reference=ref('occ_failed_body'))


def visual_facts(blobs,page_texts):
 require(len(page_texts)==2 and all(type(t) is str and not t.strip() for t in page_texts),'Saved scanned PDF has no extracted text')
 require(blobs['form_pdf'].startswith(b'%PDF-') and all(blobs[k].startswith(b'\x89PNG\r\n\x1a\n') for k in ('page1','page2')),'Original PDF and rendered page signatures')
 for key in ('form_pdf','page1','page2','root_visual_review','source_lead','capture_readback'):
  require(sha(blobs[key])==BOUND[key][1],'Hard visual evidence bytes')
 fields=[dict(page_number=1,field='1',label='Issuer name',original_text="O'REILLY AUTOMOTIVE, INC."),
  dict(page_number=1,field='8',label='Date of action',original_text='JUNE 9, 2025',normalized_date='2025-06-09'),
  dict(page_number=1,field='9',label='Classification and description',original_text='15-FOR-1 COMMON STOCK SPLIT'),
  dict(page_number=1,field='10',label='CUSIP number',original_text='67103H 107',normalized_value='67103H107',normalization='REMOVE_PRINTED_ASCII_SPACE_ONLY'),
  dict(page_number=1,field='12',label='Ticker symbol',original_text='ORLY'),
  dict(page_number=2,field='Signature date',label='Date',original_text='6/9/25',normalized_date='2025-06-09')]
 return dict(method='EXPLICIT_VISUAL_TRANSCRIPTION_BOUND_TO_SAVED_PDF_PAGES_AND_TWO_INDEPENDENT_REVIEW_RECORDS',page_count=2,
  text_extraction_empty_by_page=[True,True],fields=fields,pdf_reference=ref('form_pdf'),page_references=[ref('page1'),ref('page2')],
  independent_review_references=[ref('root_visual_review'),ref('capture_readback')],cusip_original_text='67103H 107',cusip='67103H107',
  security_class_description='COMMON STOCK',action_date='2025-06-09',signature_date='2025-06-09',publication_date=None,
  publication_date_verified=False,visual_transcription_is_not_text_parser_output=True,automated_visual_recognition_performed=False,
  signature_authenticity_verified=False,form_contains_cik_verified=False,ein_used_as_cik=False)


def assemble(docs,blobs,page_texts):
 config,snapshot,manifest=docs['config'],docs['snapshot'],docs['manifest']
 require(config['research_only'] is True and snapshot['research_only'] is True and snapshot['source_seed_sha256']==BOUND['config'][1],'Research review seed linkage')
 seed=one(config['decisions'],'decision_id','current:ORLY');saved=one(snapshot['decisions'],'decision_id','current:ORLY')
 for row in (seed,saved):require(row['tickers']==['ORLY'] and row['status']=='accepted' and row['confidence']=='high' and row['risk_chain']=='automotive','Saved accepted automotive review')
 require(seed['evidence_phrase']==saved['source_phrase']=='specialty retailers of automotive aftermarket parts' and saved['issuer_id']=='issuer:0000898173' and
  saved['security_ids']==['security:0000898173:current_ticker:ORLY'] and saved['raw_sha256']==BOUND['annual'][1]==sha(blobs['annual']),'Original current-ticker/annual hash')
 require(saved['accession_number']=='0000898173-26-000009' and saved['document_url']==URL and saved['selection_date']=='2026-07-13' and
  saved['evidence_available_date']==saved['effective_from']=='2026-02-27' and saved['allow_fallback'] is False,'Original review dates')
 require(manifest['content_sha256']==BOUND['annual'][1] and manifest['cik']=='0000898173' and manifest['accession_number']==saved['accession_number'] and
  manifest['fetched_at']=='2026-07-15T06:38:30+00:00' and manifest['fetched_at_evidence']=='sec_public_archive_http_200' and manifest['source_locator']==URL and manifest['research_only'] is True,'Annual receipt bound')
 event=docs['registry']['events'][20]
 require(event['ticker']=='ORLY' and event['raw_sha256']==BOUND['faq'][1]==sha(blobs['faq']) and event['cusip'] is None and event['publication_date'] is None and event['document_role']=='ISSUER_STOCK_SPLIT_FAQ','Old FAQ null facts remain unchanged')
 require(all(event[k] is False for k in ('point_in_time_verified','corporate_action_completeness_verified','full_provider_price_identity_binding_verified')),'Old event permissions')
 captured=capture_facts(docs,blobs);visual=visual_facts(blobs,page_texts);cover=cover_facts(blobs['annual'])
 coordinate=dict(ticker='ORLY',security_id='security:0000898173:67103H107',issuer_id='issuer:0000898173',cusip='67103H107',security_class=TITLE)
 return dict(schema='ORLY_CONDITIONAL_DATED_IDENTITY_RISK_V1',scope='CONDITIONAL_RETROSPECTIVE_RESEARCH_ONLY',**coordinate,coordinate=coordinate,
  risk_chain='automotive',conditional_risk_chain_assigned=True,research_only=True,cross_document_identity_link_is_assumption=True,saved_current_ticker_is_not_dated_identity=True,
  assumed_window=dict(first='2026-03-20',last='2026-09-21'),new_window_assumption='Common-share continuity and the saved automotive label are assumed across this window for retrospective research. Action/signature dates are not publication; July review and September local receipt do not establish early-window availability.',
  saved_review_selection_date='2026-07-13',saved_review_selection_postdates_window_start=True,annual_fetched_at=manifest['fetched_at'],
  form_received_at=docs['form_receipt']['received_at_utc'],publication_date=None,publication_date_verified=False,
  action_date=visual['action_date'],signature_date=visual['signature_date'],action_or_signature_date_used_as_publication=False,
  complete_visual_transcription=visual,complete_cover_evidence=cover,complete_capture_evidence=captured,
  saved_seed_decision=deepcopy(seed),saved_review_decision=deepcopy(saved),original_faq_registry_event=deepcopy(event),original_faq_registry_pointer='/events/20',
  annual_manifest=deepcopy(manifest),taxonomy_definition=deepcopy(docs['taxonomy']['risk_chains']['automotive']),
  input_references={k:ref(k) for k in BOUND},**dict.fromkeys(FALSE,False))


def guard(sources):
 expected=dict(sources)
 for p,h in LOADED.items():require(p not in expected or expected[p]==h,'Loaded source conflict');expected[p]=h
 for p,h in expected.items():require(sha(Path(p).read_bytes())==h,'Source bytes drift')


def build():
 sources=dict(LOADED);guard(sources);docs={};blobs={}
 for role in BOUND:
  r=ref(role);raw=Path(r['path']).read_bytes();require(sha(raw)==r['sha256'],'Hard consumed source differs');sources[r['path']]=r['sha256'];blobs[role]=raw
  if role in ('config','snapshot','taxonomy'):docs[role]=yaml.safe_load(raw)
  elif role in ('registry','manifest','index','capture_started','form_started','form_receipt','occ_started','occ_receipt'):docs[role]=json.loads(raw)
 pdf=pypdf.PdfReader(io.BytesIO(blobs['form_pdf']));pages=[page.extract_text() for page in pdf.pages]
 value=assemble(docs,blobs,pages);value['source_hashes']=sources;guard(sources);return value


def publish():
 require(not OUTPUT.parent.exists(),'Fresh fixed declaration namespace required')
 value=build();guard(value['source_hashes']);blob=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode();OUTPUT.parent.mkdir(parents=True,exist_ok=False)
 with OUTPUT.open('xb') as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
 guard(value['source_hashes']);require(OUTPUT.read_bytes()==blob and {p.name for p in OUTPUT.parent.iterdir()}=={'declaration.json'},'Publication readback drift')
 return dict(path=str(OUTPUT),sha256=sha(blob))


if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args();require(args.publish,'Explicit publish required');print(json.dumps(publish()))
