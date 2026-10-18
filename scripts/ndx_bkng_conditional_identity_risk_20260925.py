"""Saved BKNG evidence linked under explicit retrospective research assumptions."""
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
OUTPUT=BASE/'bkng_conditional_identity_risk_20260925_v1/declaration.json'
ANNUAL=ROOT/'data/cache/candidate_pools/ndx_taxonomy_v2/current_review_20260713/raw_sec/issuer_0001075531/000107553126000009/bkng-20251231.htm'
BOUND={
 'memo':(BASE/'remaining_standard_split_evidence_20260912_v1/bkng.response.bin','0d363f573ff6fbe06307c3424a2a92e0603dd36d6a3dd87f6671d331bdfa6ba1'),
 'registry':(BASE/'standard_split_exact_gap_20260919_v1/registry_readback.json','61c1a7a07f1a3ad65d3fffac43e8a8b4494c58c67192d93808333073f711c32e'),
 'annual':(ANNUAL,'62c6323e8ff6a73953cca6a1e18217e37c9c4fd883efc1a629398cac56f14fc5'),
 'manifest':(Path(str(ANNUAL)+'.manifest.json'),'0df4fb78c5725e370a09c91c8402e351d8572148810b50b7a6e6073d3bac1b65'),
 'config':(ROOT/'config/ndx_v11_current_taxonomy_review_decisions.yaml','392aea1025557a9a67bafcdc4197258970228736a7bb7b300d4bb23d7ce30c51'),
 'snapshot':(ROOT/'data/cache/candidate_pools/ndx_taxonomy_v2/current_review_20260713/reviewed/review_decisions_snapshot.yaml','2313e9f7a2b3cad2b22dca7c7f2431dd57e74a5a4cf4c3bbca2c9c8eafa87f81'),
 'taxonomy':(ROOT/'config/candidate_taxonomy_v2.yaml','3f1457a3d2de4b41f8e885ff4efb6e0f4191cf1b4463f979fb05b83af7cc1cc6'),
 'independent_source_review':(ROOT/'DYNAMIC_BKNG_INDEPENDENT_SOURCE_REVIEW_20260925.md','d412210813ffb23798549d6cd6dffcdd23d94fdc7c0c7c842b60f1d05067a42d'),
 'source_lead':(ROOT/'DYNAMIC_BKNG_SAVED_SOURCE_LEAD_20260925.md','26e44337b746832a3a1acce473c22aa073720cb99d069c1ea6bc5db8110e168a'),
 'cover_readback':(ROOT/'DYNAMIC_BKNG_MEMO_COVER_SOURCE_READBACK_20260925.md','b1421823cd64b6e3047ada20421de7a4597e09ef5f8552927e4e783953d78792')}
def sha(blob):return hashlib.sha256(blob).hexdigest()
LOADED={str(p):sha(p.read_bytes()) for p in [SOURCE,*Path(pypdf.__file__).parent.rglob('*.py'),*Path(bs4.__file__).parent.rglob('*.py'),*Path(yaml.__file__).parent.rglob('*.py')]}
FALSE=('point_in_time_verified','identity_interval_verified','risk_interval_verified','provider_binding_verified','complete_corporate_actions_verified',
 'legal_training_input_admitted','promotion_allowed','execution_authorized','fit_performed','http_performed','prices_recomputed','old_facts_modified','panel_modified',
 'direct_single_document_cusip_cik_proof','classification_uniquely_proven','sec_filing_timestamp_independently_verified','early_window_review_availability_verified',
 'early_window_local_evidence_available','runtime_binary_closure_verified','full_transitive_source_closure_reverified','option_contract_terms_used_as_equity_identity')
TITLE='Common Stock par value $0.008 per share'
URL='https://www.sec.gov/Archives/edgar/data/1075531/000107553126000009/bkng-20251231.htm'

def require(ok,message):
 if not ok:raise ValueError(message)
def ref(role):return dict(path=str(BOUND[role][0]),sha256=BOUND[role][1])
def one(rows,key,value):
 matches=[r for r in rows if r.get(key)==value];require(len(matches)==1,'Unique '+key);return matches[0]

def memo_facts(page_texts):
 require(len(page_texts)==14,'Exact memo page count')
 first=' '.join(page_texts[0].split());last=' '.join(page_texts[-1].split())
 phrases=('March 02, 2026','58460','100 Booking Holdings Inc. (BKNG) Common Shares','CUSIP:09857L108','04/06/2026')
 require(all(phrase in first for phrase in phrases),'Same first-page common shares/CUSIP/publication/ex-date')
 require('unofficial summary' in last.lower(),'Memo disclaimer required')
 return dict(page_count=14,page_number=1,publication_date='2026-03-02',ex_date='2026-04-06',cusip='09857L108',
  common_share_clause=phrases[2],cusip_clause=phrases[3],matched_phrases=[dict(text=p,normalized_offset=first.index(p)) for p in phrases],
  first_page_normalized_text=first,last_page_normalized_text=last,unofficial_summary=True,option_deliverable_is_not_equity_identity_proof=True)

def cover_facts(annual_bytes):
 soup=BeautifulSoup(annual_bytes.decode('utf-8'),'html.parser')
 def local(tag,name):return tag.name and tag.name.split(':')[-1].lower()==name
 def context(context_id):
  matches=soup.find_all(lambda tag:local(tag,'context') and tag.get('id')==context_id);require(len(matches)==1,'Unique exact context')
  tag=matches[0];identifiers=tag.find_all(lambda t:local(t,'identifier'))
  require(len(identifiers)==1 and identifiers[0].get('scheme')=='http://www.sec.gov/CIK' and identifiers[0].get_text(strip=True)=='0001075531','Context subject CIK')
  periods={name:[t.get_text(strip=True) for t in tag.find_all(lambda t:local(t,name))] for name in ('startdate','enddate')}
  require(periods=={'startdate':['2025-01-01'],'enddate':['2025-12-31']},'Context reporting interval')
  members=[dict(dimension=t.get('dimension'),member=t.get_text(strip=True)) for t in tag.find_all(lambda t:local(t,'explicitmember'))]
  return dict(context_id=context_id,entity_cik='0001075531',scheme='http://www.sec.gov/CIK',period=periods,members=members)
 c1=context('c-1');c2=context('c-2')
 require(c2['members']==[dict(dimension='us-gaap:StatementClassOfStockAxis',member='us-gaap:CommonStockMember')],'CommonStockMember axis required')
 def field(name,context_id,expected):
  tags=soup.find_all(lambda t:local(t,'nonnumeric') and t.get('name','').lower()==name.lower() and t.get('contextref')==context_id)
  require(len(tags)==1 and ' '.join(' '.join(tags[0].stripped_strings).split())==expected,'Exact same-context cover '+name)
  return dict(name=name,context=context_id,value=expected)
 fields=[field('dei:EntityCentralIndexKey','c-1','0001075531'),field('dei:DocumentPeriodEndDate','c-1','December 31 , 2025'),
  field('dei:Security12bTitle','c-2',TITLE),field('dei:TradingSymbol','c-2','BKNG')]
 text=' '.join(soup.stripped_strings);phrase='travel service provider partners';offsets=[m.start() for m in re.finditer(re.escape(phrase),text)]
 require(len(offsets)==2 and all(name in text for name in ('Booking.com','Priceline','Agoda','KAYAK','OpenTable')),'Saved business phrase and brands')
 return dict(contexts=[c1,c2],fields=fields,business_phrase=phrase,business_phrase_offsets=offsets,duplicate_phrase_is_not_independent_evidence=True,
  text_normalization='BeautifulSoup_html.parser_stripped_strings_single_space_join',normalized_text_sha256=sha(text.encode()))

def assemble(docs,annual_bytes,page_texts):
 config,snapshot,manifest=docs['config'],docs['snapshot'],docs['manifest'];event=docs['registry']['events'][2]
 require(config['research_only'] is True and snapshot['research_only'] is True and snapshot['source_seed_sha256']==BOUND['config'][1],'Saved research seed linkage')
 seed=one(config['decisions'],'decision_id','current:BKNG');saved=one(snapshot['decisions'],'decision_id','current:BKNG')
 for row in (seed,saved):require(row['tickers']==['BKNG'] and row['status']=='accepted' and row['confidence']=='high' and row['risk_chain']=='travel_hospitality','Saved accepted risk decision')
 require(seed['evidence_phrase']==saved['source_phrase']=='travel service provider partners' and saved['issuer_id']=='issuer:0001075531' and
  saved['security_ids']==['security:0001075531:current_ticker:BKNG'] and saved['raw_sha256']==BOUND['annual'][1]==sha(annual_bytes),'Saved current-ticker/annual binding')
 require(saved['accession_number']=='0001075531-26-000009' and saved['document_url']==URL and saved['selection_date']=='2026-07-13' and
  saved['evidence_available_date']==saved['effective_from']=='2026-02-18' and saved['allow_fallback'] is False,'Saved late review dates')
 require(manifest['content_sha256']==BOUND['annual'][1] and manifest['cik']=='0001075531' and manifest['accession_number']==saved['accession_number'] and
  manifest['fetched_at']=='2026-07-15T06:38:46+00:00' and manifest['fetched_at_evidence']=='sec_public_archive_http_200' and manifest['source_locator']==URL,'Saved annual receipt')
 require(event['ticker']=='BKNG' and event['raw_sha256']==BOUND['memo'][1] and event['cusip']=='09857L108' and event['security_class']=='COMMON' and
  event['publication_date']=='2026-03-02' and event['first_adjusted_trading_date']=='2026-04-06' and event['received_at_utc']=='2026-09-11T21:04:19.470604+00:00','Registry event2 memorandum binding')
 require(all(event[k] is False for k in ('point_in_time_verified','corporate_action_completeness_verified','full_provider_price_identity_binding_verified')),'No event authority upgrade')
 memo=memo_facts(page_texts);cover=cover_facts(annual_bytes)
 return dict(schema='BKNG_CONDITIONAL_DATED_IDENTITY_RISK_V1',scope='CONDITIONAL_RETROSPECTIVE_RESEARCH_ONLY',ticker='BKNG',security_id='security:0001075531:09857L108',issuer_id='issuer:0001075531',cusip='09857L108',security_class=TITLE,
  coordinate=dict(ticker='BKNG',security_id='security:0001075531:09857L108',issuer_id='issuer:0001075531',cusip='09857L108',security_class=TITLE),
  risk_chain='travel_hospitality',conditional_risk_chain_assigned=True,research_only=True,cross_document_identity_link_is_assumption=True,saved_current_ticker_is_not_dated_identity=True,
  assumed_window=dict(first='2026-03-20',last='2026-09-21'),new_window_assumption='Ordinary-share continuity and the saved travel_hospitality label are assumed across this window for retrospective research; July review and later local receipts do not prove early-window availability.',
  saved_review_selection_date='2026-07-13',annual_fetched_at=manifest['fetched_at'],memo_received_at=event['received_at_utc'],saved_review_selection_postdates_window_start=True,
  complete_memo_evidence=memo,complete_cover_evidence=cover,saved_seed_decision=deepcopy(seed),saved_review_decision=deepcopy(saved),registry_event=deepcopy(event),registry_event_pointer='/events/2',
  annual_manifest=deepcopy(manifest),taxonomy_definition=deepcopy(docs['taxonomy']['risk_chains']['travel_hospitality']),
  input_references={k:ref(k) for k in BOUND},**dict.fromkeys(FALSE,False))

def guard(sources):
 expected=dict(sources)
 for p,h in LOADED.items():require(p not in expected or expected[p]==h,'Loaded source conflict');expected[p]=h
 for p,h in expected.items():require(sha(Path(p).read_bytes())==h,'Source bytes drift')

def build():
 sources=dict(LOADED);guard(sources);docs={};blobs={}
 for role in BOUND:
  r=ref(role);raw=Path(r['path']).read_bytes();require(sha(raw)==r['sha256'],'Hard source differs');sources[r['path']]=r['sha256'];blobs[role]=raw
  if role in ('config','snapshot','taxonomy'):docs[role]=yaml.safe_load(raw)
  elif role in ('registry','manifest'):docs[role]=json.loads(raw)
 pdf=pypdf.PdfReader(io.BytesIO(blobs['memo']));pages=[page.extract_text() for page in pdf.pages]
 value=assemble(docs,blobs['annual'],pages);value['source_hashes']=sources;guard(sources);return value

def publish():
 require(not OUTPUT.parent.exists(),'Fresh fixed declaration namespace required')
 value=build();guard(value['source_hashes']);blob=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode();OUTPUT.parent.mkdir(parents=True,exist_ok=False)
 with OUTPUT.open('xb') as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
 guard(value['source_hashes']);require(OUTPUT.read_bytes()==blob and {p.name for p in OUTPUT.parent.iterdir()}=={'declaration.json'},'Publication readback drift')
 return dict(path=str(OUTPUT),sha256=sha(blob))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args();require(args.publish,'Explicit publish required');print(json.dumps(publish()))
