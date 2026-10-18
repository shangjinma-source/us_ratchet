"""Saved CTAS evidence linked under explicit retrospective research assumptions."""
import argparse
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
from email import policy
from email.parser import BytesParser
from datetime import datetime
try:
 import pypdf
except ModuleNotFoundError:
 sys.path.append(str(Path('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/Lib/site-packages')))
 import pypdf
import bs4
from bs4 import BeautifulSoup
import yaml
SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];BASE=ROOT/'data/cache/research'
OUTPUT=BASE/'ctas_conditional_identity_risk_20260925_v1/declaration.json'
BOUND={
 'memo_raw':(ROOT/'data/cache/research/ctas_identity_evidence_capture_20260925_v1/ctas_memo.response.bin','d5fc66d1a471a960182941cc31e0e3f07b4a518abc737abadd59e603d9fb2028'),
 'memo':(ROOT/'data/cache/research/ctas_identity_evidence_capture_20260925_v1/ctas_memo.extracted.pdf','84bc8b70aa9296897443ede77e06658d6b93271d31fbc29f64acd278c15b988b'),
 'capture_started':(ROOT/'data/cache/research/ctas_identity_evidence_capture_20260925_v1/started.json','60c952fe74d57da5e4e7e56e9cfcf4ac1f5b852644c16a1fedd087a057224ab0'),
 'capture_receipt':(ROOT/'data/cache/research/ctas_identity_evidence_capture_20260925_v1/receipt.json','298e0bd7a29be7c581cffa34830d06c26a491c1762d6b00749551ccb537bb99b'),
 'extraction':(ROOT/'data/cache/research/ctas_identity_evidence_capture_20260925_v1/extraction.json','878781efd9c5173994331f969dd9ddd91f15318b3fc3524144d0d5b0485929d6'),
 'registry':(ROOT/'data/cache/research/standard_split_exact_gap_20260919_v1/registry_readback.json','61c1a7a07f1a3ad65d3fffac43e8a8b4494c58c67192d93808333073f711c32e'),
 'annual':(ROOT/'data/cache/candidate_pools/ndx_taxonomy_v2/current_review_20260713/raw_sec/issuer_0000723254/000072325425000017/ctas-20250531.htm','78495a5265b6b3e93c5ceb5f11f5e699db5e5f873b6db40aa400dc2f394fdf27'),
 'config':(ROOT/'config/ndx_v11_current_taxonomy_review_decisions.yaml','392aea1025557a9a67bafcdc4197258970228736a7bb7b300d4bb23d7ce30c51'),
 'snapshot':(ROOT/'data/cache/candidate_pools/ndx_taxonomy_v2/current_review_20260713/reviewed/review_decisions_snapshot.yaml','2313e9f7a2b3cad2b22dca7c7f2431dd57e74a5a4cf4c3bbca2c9c8eafa87f81'),
 'taxonomy':(ROOT/'config/candidate_taxonomy_v2.yaml','3f1457a3d2de4b41f8e885ff4efb6e0f4191cf1b4463f979fb05b83af7cc1cc6'),
 'root_readback':(ROOT/'DYNAMIC_CTAS_NEW_MEMO_ROOT_READBACK_20260925.md','d25730061a0638c24a021e7596206088307a0d054301de1b97b21f296cbb49b9'),
 'independent_source_review':(ROOT/'DYNAMIC_CTAS_SAVED_IDENTITY_RISK_SOURCE_REVIEW_20260925.md','ffb6117f958fb75d892b1fd9b7db42c1a200e33792a016e318f89ea03d81cbfc'),
 'manifest':(ROOT/'data/cache/candidate_pools/ndx_taxonomy_v2/current_review_20260713/raw_sec/issuer_0000723254/000072325425000017/ctas-20250531.htm.manifest.json','c3a6961500e2d06eaf784b126be714fbd9feb36feb1f8b3616e5db46bf380ee7'),
 'visual_page1':(ROOT/'data/cache/research/ctas_identity_evidence_visual_20260925_v1/page-1.png','6f2e8b834bea25a6f33f648a7535be0eb447d05e1a834127dc7196b59a1f75e7'),
 'visual_page3':(ROOT/'data/cache/research/ctas_identity_evidence_visual_20260925_v1/page-3.png','1fa38ee6fb8f1e4eea1bd1b70647b16e9ca40a7a53e609732cfdf4fea591e1ea'),
 'visual_page4':(ROOT/'data/cache/research/ctas_identity_evidence_visual_20260925_v1/page-4.png','f7cd7feb6aea3269e2007d4b9f4ee3f6627858fbc1c63f22b669462e595f6a7a'),
}

def sha(blob):return hashlib.sha256(blob).hexdigest()
LOADED={str(p):sha(p.read_bytes()) for p in [SOURCE,*Path(pypdf.__file__).parent.rglob('*.py'),*Path(bs4.__file__).parent.rglob('*.py'),*Path(yaml.__file__).parent.rglob('*.py')]}
FALSE=('point_in_time_verified','identity_interval_verified','risk_interval_verified','provider_binding_verified','complete_corporate_actions_verified',
 'legal_training_input_admitted','promotion_allowed','execution_authorized','fit_performed','http_performed','prices_recomputed','old_facts_modified','panel_modified',
 'direct_single_document_cusip_cik_proof','classification_uniquely_proven','sec_filing_timestamp_independently_verified','early_window_review_availability_verified',
 'early_window_local_evidence_available','runtime_binary_closure_verified','full_transitive_source_closure_reverified','option_contract_terms_used_as_equity_identity','live_execution_authorized')
TITLE='Common stock, no par value'
URL='https://www.sec.gov/Archives/edgar/data/723254/000072325425000017/ctas-20250531.htm'
MEMO_URL='https://www.miaxglobal.com/sites/default/files/alert-files/CTAS_Split_55082.pdf'

def require(ok,message):
 if not ok:raise ValueError(message)
def ref(role):return dict(path=str(BOUND[role][0]),sha256=BOUND[role][1])
def one(rows,key,value):
 matches=[r for r in rows if r.get(key)==value];require(len(matches)==1,'Unique '+key);return matches[0]

def multipart_evidence(raw,derived,docs):
 started,receipt,extraction=(docs[k] for k in ('capture_started','capture_receipt','extraction'))
 require(type(started['attempt']) is int and started['attempt']==1 and started['retry_allowed'] is False and started['url']==MEMO_URL,'Single original capture')
 require(receipt['requested_url']==receipt['final_url']==MEMO_URL and type(receipt['http_status']) is int and receipt['http_status']==200 and receipt['content_type']=='application/pdf','Original capture metadata')
 require(receipt['body_reference']==ref('memo_raw') and receipt['started_reference']==ref('capture_started') and receipt['content_bytes']==len(raw) and receipt['point_in_time_verified'] is False,'Capture byte/reference link')
 require(started['started_at_utc']=='2026-09-24T18:15:55.426855+00:00' and receipt['received_at_utc']=='2026-09-24T18:15:56.892204+00:00','Actual late UTC timestamps')
 require(datetime.fromisoformat(started['started_at_utc'])<datetime.fromisoformat(receipt['received_at_utc']),'Receipt ordering')
 require(sha(raw)==BOUND['memo_raw'][1] and sha(derived)==BOUND['memo'][1],'Raw and derived are separately pinned')
 first=raw.split(b'\r\n',1)[0];require(first.startswith(b'--') and len(first)>2,'Multipart boundary')
 boundary=first[2:];require(all(32<c<127 and c!=34 for c in boundary),'ASCII boundary')
 message=BytesParser(policy=policy.default).parsebytes(b'Content-Type: multipart/form-data; boundary="'+boundary+b'"\r\nMIME-Version: 1.0\r\n\r\n'+raw)
 require(message.is_multipart() and not message.defects,'Well-formed original multipart')
 parts=list(message.iter_parts());require(len(parts)==1 and not parts[0].defects and not parts[0].is_multipart(),'Exactly one PDF part')
 part=parts[0];require(part.get_filename()=='CTAS_Split_55082.pdf' and part.get_content_type()=='application/octet-stream' and part.get('Content-Transfer-Encoding')=='binary','Original part headers')
 require(part.get_payload(decode=True)==derived and derived.startswith(b'%PDF-') and raw.count(derived)==1 and raw.find(derived)==195,'Exact unique contiguous derived PDF')
 require(extraction==dict(schema='SINGLE_MULTIPART_PDF_EXTRACTION_V1',derived_bytes=len(derived),derived_sha256=sha(derived),filename='CTAS_Split_55082.pdf',network_repeated=False,part_count=1,payload_start_offset=195,raw_bytes=len(raw),raw_modified=False,raw_sha256=sha(raw)),'Complete saved extraction relationship')
 return dict(original_started=deepcopy(started),original_receipt=deepcopy(receipt),original_extraction=deepcopy(extraction),strict_single_part_payload_exact=True,original_body_is_pdf_without_multipart=False)


def memo_facts(page_texts):
 require(len(page_texts)==4,'Exact four-page memorandum')
 texts=[' '.join(t.split()) for t in page_texts];first=texts[0]
 phrases=('August 21, 2024','#55082','100 Cintas Corporation (CTAS) Common Shares','CUSIP:172908105','09/12/2024','4 for 1 stock split')
 require(all(p in first for p in phrases),'Same first-page dated identity facts')
 require('unofficial summary' in texts[2].lower(),'Third-page disclaimer')
 return dict(page_count=4,page_number=1,publication_date='2024-08-21',publication_date_role='MEMORANDUM_PRINTED_DATE_NOT_LOCAL_AVAILABILITY',ex_date='2024-09-12',cusip='172908105',security_class_in_memo='Common Shares',matched_phrases=[dict(text=p,normalized_offset=first.index(p)) for p in phrases],normalized_page_texts=texts,disclaimer_page=3,unofficial_summary=True,option_deliverable_is_not_equity_identity_proof=True)


def cover_facts(annual_bytes):
 soup=BeautifulSoup(annual_bytes.decode('utf-8'),'html.parser')
 def local(tag,name):return tag.name and tag.name.split(':')[-1].lower()==name
 contexts=soup.find_all(lambda t:local(t,'context') and t.get('id')=='c-1');require(len(contexts)==1,'Unique subject context')
 ctx=contexts[0];identifiers=ctx.find_all(lambda t:local(t,'identifier'))
 require(len(identifiers)==1 and identifiers[0].get('scheme')=='http://www.sec.gov/CIK' and identifiers[0].get_text(strip=True)=='0000723254','Subject CIK context')
 periods={k:[t.get_text(strip=True) for t in ctx.find_all(lambda t:local(t,k))] for k in ('startdate','enddate')}
 require(periods==dict(startdate=['2024-06-01'],enddate=['2025-05-31']) and not ctx.find_all(lambda t:local(t,'explicitmember')),'Unsegmented annual reporting context')
 fields=[]
 for name,expected in [('EntityCentralIndexKey','0000723254'),('EntityRegistrantName','Cintas Corporation'),('TradingSymbol','CTAS'),('Security12bTitle',TITLE)]:
  tags=soup.find_all(lambda t:local(t,'nonnumeric') and t.get('name','').lower()=='dei:'+name.lower() and t.get('contextref')=='c-1')
  require(len(tags)==1 and ' '.join(' '.join(tags[0].stripped_strings).split())==expected,'Same-context cover '+name)
  fields.append(dict(name='dei:'+name,context='c-1',value=expected))
 text=' '.join(soup.stripped_strings);phrase='uniforms, mats, mops, shop towels';offsets=[m.start() for m in re.finditer(re.escape(phrase),text)]
 require(bool(offsets),'Original business phrase')
 return dict(context_id='c-1',entity_cik='0000723254',period=periods,fields=fields,business_phrase=phrase,business_phrase_offsets=offsets,text_normalization='BeautifulSoup_html.parser_stripped_strings_single_space_join',normalized_text_sha256=sha(text.encode()))


def assemble(docs,annual_bytes,page_texts,capture):
 config,snapshot,manifest=docs['config'],docs['snapshot'],docs['manifest'];event=docs['registry']['events'][6]
 require(config['research_only'] is True and snapshot['research_only'] is True and snapshot['source_seed_sha256']==BOUND['config'][1],'Saved research seed linkage')
 seed=one(config['decisions'],'decision_id','current:CTAS');saved=one(snapshot['decisions'],'decision_id','current:CTAS')
 for row in (seed,saved):require(row['tickers']==['CTAS'] and row['status']=='accepted' and row['confidence']=='high' and row['risk_chain']=='industrial','Saved accepted industrial decision')
 require(seed['evidence_phrase']==saved['source_phrase']=='uniforms, mats, mops, shop towels' and saved['issuer_id']=='issuer:0000723254' and saved['security_ids']==['security:0000723254:current_ticker:CTAS'] and saved['raw_sha256']==BOUND['annual'][1]==sha(annual_bytes),'Saved current-ticker annual binding')
 require(saved['accession_number']=='0000723254-25-000017' and saved['document_url']==URL and saved['selection_date']=='2026-07-13' and saved['evidence_available_date']==saved['effective_from']=='2025-07-28' and saved['allow_fallback'] is False,'Saved dates and source')
 require(manifest['content_sha256']==BOUND['annual'][1] and manifest['cik']=='0000723254' and manifest['accession_number']==saved['accession_number'] and manifest['fetched_at']=='2026-07-15T06:38:08+00:00' and manifest['fetched_at_evidence']=='sec_public_archive_http_200' and manifest['source_locator']==URL and manifest['research_only'] is True,'Saved annual receipt')
 require(event['ticker']=='CTAS' and event['raw_sha256']==BOUND['annual'][1] and event['cusip'] is None and event['publication_date'] is None and event['issuer_cik']=='0000723254' and event['security_class']=='COMMON' and event['first_adjusted_trading_date']=='2024-09-12','Original registry nulls preserved')
 require(all(event[k] is False for k in ('point_in_time_verified','corporate_action_completeness_verified','full_provider_price_identity_binding_verified')),'No original event authority')
 require(capture['strict_single_part_payload_exact'] is True and capture['original_receipt']==docs['capture_receipt'],'Verified capture evidence')
 coordinate=dict(ticker='CTAS',security_id='security:0000723254:172908105',issuer_id='issuer:0000723254',cusip='172908105',security_class=TITLE)
 return dict(schema='CTAS_CONDITIONAL_DATED_IDENTITY_RISK_V1',scope='CONDITIONAL_RETROSPECTIVE_RESEARCH_ONLY',**coordinate,coordinate=coordinate,
  risk_chain='industrial',conditional_risk_chain_assigned=True,research_only=True,cross_document_identity_link_is_assumption=True,saved_current_ticker_is_not_dated_identity=True,
  assumed_window=dict(first='2026-03-20',last='2026-09-21'),new_window_assumption='Ordinary-share continuity and saved industrial risk are retrospective assumptions; the memo does not prove joint CIK/CUSIP or early-window local availability.',
  saved_review_selection_date='2026-07-13',annual_fetched_at=manifest['fetched_at'],memo_received_at=docs['capture_receipt']['received_at_utc'],saved_review_selection_postdates_window_start=True,
  complete_memo_evidence=memo_facts(page_texts),complete_cover_evidence=cover_facts(annual_bytes),complete_capture_evidence=deepcopy(capture),saved_seed_decision=deepcopy(seed),saved_review_decision=deepcopy(saved),registry_event=deepcopy(event),registry_event_pointer='/events/6',
  annual_manifest=deepcopy(manifest),taxonomy_definition=deepcopy(docs['taxonomy']['risk_chains']['industrial']),input_references={k:ref(k) for k in BOUND},**dict.fromkeys(FALSE,False))


def guard(sources):
 expected=dict(sources)
 for p,h in LOADED.items():require(p not in expected or expected[p]==h,'Loaded source conflict');expected[p]=h
 for p,h in expected.items():require(sha(Path(p).read_bytes())==h,'Source bytes drift')

def build():
 sources=dict(LOADED);guard(sources);docs={};blobs={}
 for role in BOUND:
  r=ref(role);raw=Path(r['path']).read_bytes();require(sha(raw)==r['sha256'],'Hard source differs');sources[r['path']]=r['sha256'];blobs[role]=raw
  if role in ('config','snapshot','taxonomy'):docs[role]=yaml.safe_load(raw)
  elif role in ('registry','manifest','capture_started','capture_receipt','extraction'):docs[role]=json.loads(raw)
 pdf=pypdf.PdfReader(io.BytesIO(blobs['memo']));pages=[page.extract_text() for page in pdf.pages]
 capture=multipart_evidence(blobs['memo_raw'],blobs['memo'],docs)
 value=assemble(docs,blobs['annual'],pages,capture);value['source_hashes']=sources;guard(sources);return value

def publish():
 require(not OUTPUT.parent.exists(),'Fresh fixed declaration namespace required')
 value=build();guard(value['source_hashes']);blob=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode();OUTPUT.parent.mkdir(parents=True,exist_ok=False)
 with OUTPUT.open('xb') as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
 guard(value['source_hashes']);require(OUTPUT.read_bytes()==blob and {p.name for p in OUTPUT.parent.iterdir()}=={'declaration.json'},'Publication readback drift')
 return dict(path=str(OUTPUT),sha256=sha(blob))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args();require(args.publish,'Explicit publish required');print(json.dumps(publish()))
