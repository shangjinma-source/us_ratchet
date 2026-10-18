"""Source-bound saved CPRT research decision; no identity or interval certification."""
import argparse
from copy import deepcopy
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import yaml
SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];BASE=ROOT/'data/cache/research'
OUTPUT=BASE/'cprt_saved_risk_adjudication_20260925_v1/adjudication.json'
BOUND={
 'config':(ROOT/'config/ndx_v11_current_taxonomy_review_decisions.yaml','392aea1025557a9a67bafcdc4197258970228736a7bb7b300d4bb23d7ce30c51'),
 'snapshot':(ROOT/'data/cache/candidate_pools/ndx_taxonomy_v2/current_review_20260713/reviewed/review_decisions_snapshot.yaml','2313e9f7a2b3cad2b22dca7c7f2431dd57e74a5a4cf4c3bbca2c9c8eafa87f81'),
 'annual':(ROOT/'data/cache/candidate_pools/ndx_taxonomy_v2/current_review_20260713/raw_sec/issuer_0000900075/000162828025042946/cprt-20250731.htm','bc5f78bd9812699603d3201bce9142fcaf957e590212384e3363854fd734e0b9'),
 'identity':(BASE/'pcar_cprt_conditional_identity_20260923_v1/facts.json','e187cea1c8df1a8e87a156abbcebef402c23ea711d871e2387f17dac19b60402'),
 'business':(BASE/'pcar_cprt_conditional_identity_20260923_v1/business_facts.json','9f1aa79f928f6cbfe046e657f9c65a7e4afe5c7736f86e9b333a73a051a72ca0'),
 'taxonomy':(ROOT/'config/candidate_taxonomy_v2.yaml','3f1457a3d2de4b41f8e885ff4efb6e0f4191cf1b4463f979fb05b83af7cc1cc6'),
 'report':(ROOT/'DYNAMIC_CPRT_SAVED_RISK_SOURCE_REVIEW_20260925.md','8e7b91546b4622a9fc269a4568705e5d7d285b7dfbebc5e5d5b8bcade9108a77')}
def sha(blob):return hashlib.sha256(blob).hexdigest()
LOADED={str(p):sha(p.read_bytes()) for p in [SOURCE,*Path(yaml.__file__).parent.rglob('*.py')]}
FALSE=('point_in_time_verified','identity_interval_verified','risk_interval_verified','provider_binding_verified','complete_corporate_actions_verified','legal_training_input_admitted','promotion_allowed','execution_authorized','fit_performed','http_performed','old_facts_modified','panel_modified','direct_single_document_cusip_cik_proof','classification_uniquely_proven','sec_filing_timestamp_independently_verified','historical_review_transitive_sources_reverified','runtime_binary_closure_verified','early_window_review_availability_verified')
PHRASES=('We are a leading global provider of online auctions and vehicle remarketing services',
 'We provide vehicle sellers with a full range of services to process and sell vehicles primarily over the internet through our Virtual Bidding Third Generation internet auction-style sales technology, which we refer to as VB3.',
 'Vehicle sellers consist primarily of insurance companies')
URL='https://www.sec.gov/Archives/edgar/data/900075/000162828025042946/cprt-20250731.htm'

def require(ok,message):
 if not ok:raise ValueError(message)
def ref(role):return dict(path=str(BOUND[role][0]),sha256=BOUND[role][1])
def one(rows,key,value):
 matches=[r for r in rows if r.get(key)==value];require(len(matches)==1,'Unique '+key);return matches[0]
class Text(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.parts=[];self.active=[];self.fields={}
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='ix:nonnumeric':self.active.append((a.get('name','').lower(),a.get('contextref'),[]))
 def handle_data(self,data):
  self.parts.append(data)
  for _,_,pieces in self.active:pieces.append(data)
 def handle_endtag(self,tag):
  if tag=='ix:nonnumeric' and self.active:
   name,context,pieces=self.active.pop();self.fields.setdefault(name,[]).append((context,' '.join(''.join(pieces).split())))

def assemble(documents,annual_bytes):
 config,snapshot,identity,business,taxonomy=(documents[k] for k in ('config','snapshot','identity','business','taxonomy'))
 require(config['research_only'] is True and snapshot['research_only'] is True and config['taxonomy_id']==snapshot['taxonomy_id']=='us_growth_risk_chain_taxonomy_v2','Research-only taxonomy scope')
 require(snapshot['source_seed_sha256']==BOUND['config'][1],'Snapshot exact seed linkage')
 seed=one(config['decisions'],'decision_id','current:CPRT');saved=one(snapshot['decisions'],'decision_id','current:CPRT')
 for row in (seed,saved):require(row['tickers']==['CPRT'] and row['risk_chain']=='automotive' and row['confidence']=='high' and row['status']=='accepted','Saved automotive decision')
 require(seed['evidence_phrase']==saved['source_phrase']=='online auctions and vehicle remarketing services','Exact operative phrase')
 require(saved['issuer_id']=='issuer:0000900075' and saved['security_ids']==['security:0000900075:current_ticker:CPRT'] and saved['form']=='10-K' and saved['accession_number']=='0001628280-25-042946' and saved['document_url']==URL and saved['raw_sha256']==BOUND['annual'][1]==sha(annual_bytes),'Exact annual/source/current-ticker linkage')
 require(saved['effective_from']==saved['evidence_available_date']=='2025-09-26' and saved['selection_date']=='2026-07-13' and saved['effective_to']=='' and saved['allow_fallback'] is False,'Saved dates and nonfallback scope')
 old_identity=one(identity['rows'],'ticker','CPRT');old_business=one(business['rows'],'ticker','CPRT')
 require(old_identity['conditional_research_security_id']=='security:0000900075:217204106' and old_identity['issuer_id']=='issuer:0000900075' and old_identity['cusip']=='217204106' and old_identity['security_class']=='Common Stock, par value $0.0001' and old_identity['risk_chain'] is None and old_identity['risk_chain_assigned'] is False,'Original conditional identity remains risknull')
 require(old_identity['issuer_link_is_cross_document_research_assumption'] is True and old_identity['direct_single_document_cusip_cik_proof'] is False,'No direct CUSIP proof')
 require(old_business['issuer_id']=='issuer:0000900075' and old_business['assigned_risk_chain'] is None and old_business['risk_chain_assigned'] is False and old_business['boundary_status']=='UNRESOLVED_EXISTING_ALTERNATIVES' and old_business['candidate_risk_chains']==['internet_ecommerce','automotive','industrial'],'Preserve original unresolved alternatives')
 parser=Text();parser.feed(annual_bytes.decode('utf-8'));text=' '.join(' '.join(parser.parts).split())
 expected={'dei:entitycentralindexkey':'0000900075','dei:tradingsymbol':'CPRT','dei:security12btitle':'Common Stock, par value $0.0001','dei:documentperiodenddate':'July 31, 2025'};contexts=[]
 for key,value in expected.items():
  fields=parser.fields.get(key,[]);require(len(fields)==1 and fields[0][1]==value,'Unique annual cover '+key);contexts.append(fields[0][0])
 require(len(set(contexts))==1,'Same-context annual cover')
 clauses=[]
 for phrase in PHRASES:
  offsets=[];start=0
  while True:
   offset=text.find(phrase,start)
   if offset<0:break
   offsets.append(offset);start=offset+len(phrase)
  require(offsets,'Original business clause missing')
  clauses.append(dict(text=phrase,normalized_text_offset=offsets[0],all_normalized_text_offsets=offsets,occurrence_count=len(offsets),reference_occurrence_index=0,reference_role='FIRST_OCCURRENCE_BUSINESS_TEXT_REPEATED_IN_MDA_OR_NOTES_NOT_ADDITIONAL_PROOF',text_sha256=sha(phrase.encode())))
 # Only the saved category definition is adopted; alternatives remain in the old row.
 definitions=taxonomy['risk_chains'];require(business['source_hashes'].get(str(BOUND['taxonomy'][0]))==BOUND['taxonomy'][1],'Saved business taxonomy source SHA linkage')
 require('automotive' in definitions and 'automotive' in business['taxonomy_definitions'],'Automotive category key retained')
 return dict(schema='CPRT_SAVED_RISK_CONDITIONAL_ADJUDICATION_V1',scope='SAVED_RESEARCH_DECISION_REUSED_UNDER_NEW_EXPLICIT_WINDOW_ASSUMPTION',ticker='CPRT',security_id=old_identity['conditional_research_security_id'],issuer_id=old_identity['issuer_id'],cusip=old_identity['cusip'],security_class=old_identity['security_class'],risk_chain='automotive',conditional_risk_chain_assigned=True,research_only=True,
  assumed_window=dict(first='2026-03-20',last='2026-09-21'),new_window_assumption='The saved automotive research classification and cross-document dated identity are assumed to continue through this window; the July 13, 2026 saved review postdates the window start, so this is a retrospective conditional use, not proof that the review was available at window start; continuity, provider binding and PIT are not established.',
  saved_review_selection_postdates_window_start=True,saved_current_ticker_id_is_not_dated_cusip_proof=True,cross_document_identity_link_is_assumption=True,saved_review_dates_are_not_newly_verified_availability=True,
  original_identity_fact=deepcopy(old_identity),original_business_fact=deepcopy(old_business),saved_seed_decision=deepcopy(seed),saved_review_decision=deepcopy(saved),taxonomy_definition=deepcopy(definitions['automotive']),original_business_taxonomy_definitions=deepcopy(business['taxonomy_definitions']),saved_and_current_taxonomy_text_exact=(definitions['automotive']==business['taxonomy_definitions']['automotive']),taxonomy_text_projection_policy='PRESERVE_SAVED_TEXT_WITHOUT_ENCODING_REPAIR_USE_DIRECT_HARD_TAXONOMY_DEFINITION',original_cover_fields={k:parser.fields[k] for k in expected},business_clauses=clauses,text_normalization='STDLIB_HTMLPARSER_DATA_WHITESPACE_ONLY_UTF8_NO_ENCODING_REPAIR',source_role='2025_ANNUAL_BUSINESS_AND_SAVED_RESEARCH_DECISION_NOT_NEW_PIT_CERTIFICATION',input_references={k:ref(k) for k in BOUND},**dict.fromkeys(FALSE,False))

def guard(sources):
 expected=dict(sources)
 for p,h in LOADED.items():require(p not in expected or expected[p]==h,'Loaded source conflict');expected[p]=h
 for p,h in expected.items():require(sha(Path(p).read_bytes())==h,'Source drift')
def build():
 sources=dict(LOADED);guard(sources);blobs={}
 for key,(path,h) in BOUND.items():
  blob=path.read_bytes();require(sha(blob)==h,'Consumed source bytes differ');blobs[key]=blob;sources[str(path)]=h
 documents={k:(json.loads(blobs[k]) if k in ('identity','business') else yaml.safe_load(blobs[k].decode('utf-8'))) for k in ('config','snapshot','identity','business','taxonomy')}
 result=assemble(documents,blobs['annual']);result['source_hashes']=sources;guard(sources);return result

def build_and_publish():
 require(not OUTPUT.parent.exists(),'Fresh immutable declaration namespace required')
 result=build();guard(result['source_hashes']);blob=(json.dumps(result,sort_keys=True,indent=2,ensure_ascii=True,allow_nan=False)+'\n').encode()
 OUTPUT.parent.mkdir(parents=True,exist_ok=False)
 with OUTPUT.open('xb') as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
 guard(result['source_hashes']);require(OUTPUT.read_bytes()==blob and {p.name for p in OUTPUT.parent.iterdir()}=={'adjudication.json'},'Output bytes/namespace drift')
 return dict(path=str(OUTPUT),sha256=sha(blob))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--publish',action='store_true');args=p.parse_args();require(args.publish,'Explicit publish required');print(json.dumps(build_and_publish()))
