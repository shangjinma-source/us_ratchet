"""Independent byte/reference and saved HTML evidence readback. No producer imports."""
import csv, hashlib, io, json, re
from pathlib import Path
from html.parser import HTMLParser
import yaml
ROOT=Path(__file__).resolve().parents[1]
DIRECTORY=ROOT/'data/cache/research/full_pool_saved_evidence_batch_20261002_v1'
BATCH='53e2c75e4f317ba1ced555a3821669d2a73d2c3bd49c89c73aecd1f147441a69'
PUBLICATION='e4d728fee63cee0f764e4e5d83015672e11a1a466e7bc2fa57d7d761c5ab87a2'
def check(ok,label):
    if not ok: raise ValueError(label)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def norm(value):return ' '.join(value.split())
def load(ref):
    raw=Path(ref['path']).read_bytes();check(sha(raw)==ref['sha256'],'SHA '+ref['path']);return raw
def exact(a,b):return json.dumps(a,sort_keys=True,ensure_ascii=False)==json.dumps(b,sort_keys=True,ensure_ascii=False)

class EvidenceLocator(HTMLParser):
    """Streaming text locator; captures only evidence elements, not an extractor output."""
    def __init__(self):
        super().__init__(convert_charrefs=True);self.stack=[];self.nodes={};self.visible=[];self.serial=0
    def handle_starttag(self,tag,attrs):
        self.serial+=1;a=dict(attrs);local=tag.split(':')[-1]
        hidden=any(n['hidden'] for n in self.stack) or local=='hidden' or 'hidden' in a or bool(re.search(r'display\s*:\s*none|visibility\s*:\s*hidden',a.get('style','') or '',re.I))
        node={'tag':tag,'attrs':a,'hidden':hidden,'pieces':[],'index':self.serial}
        self.nodes[self.serial]=node
        if local not in {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}:self.stack.append(node)
    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if self.stack and self.stack[-1]['tag']==tag:self.stack.pop()
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i]['tag']==tag:del self.stack[i:];break
    def handle_data(self,text):
        if not any(n['hidden'] or n['tag'].split(':')[-1] in {'script','style'} for n in self.stack):self.visible.append(text)
        excluded=[i for i,n in enumerate(self.stack) if n['tag'].split(':')[-1]=='exclude']
        for i,n in enumerate(self.stack):
            if excluded and i<=max(excluded):continue
            if n['tag'].split(':')[-1] in {'nonnumeric','nonfraction','fraction','continuation','context','identifier','startdate','enddate','instant','forever','explicitmember','typedmember'}:n['pieces'].append(text)
    def text(self,index):return norm(' '.join(self.nodes[index]['pieces']))

def verify():
    b=json.loads(load({'path':str(DIRECTORY/'batch.json'),'sha256':BATCH}))
    p=json.loads(load({'path':str(DIRECTORY/'publication.json'),'sha256':PUBLICATION}))
    check(p['batch_reference']=={'path':str(DIRECTORY/'batch.json'),'sha256':BATCH},'publication binding')
    check(p['source_hashes']==b['source_hashes'],'source maps')
    start=json.loads((DIRECTORY/'started.json').read_bytes());check(start['source_hashes']==b['source_hashes'],'started map')
    check(not b['missing_source_paths'] and not start['missing_source_paths'],'missing paths')
    for path,digest in b['source_hashes'].items():load({'path':path,'sha256':digest})
    inv=b['inventory_preserved'];docs={};refs=inv['input_references']
    for role,ref in refs.items():
        raw=load(ref)
        docs[role]=(list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))) if role in {'identities','nport','exact_events'} else yaml.safe_load(raw.decode('utf-8-sig')) if role in {'scope','review'} else json.loads(raw))
    def deref(ref):
        role=next(k for k,v in refs.items() if v['path']==ref['path'] and v['sha256']==ref['sha256']);value=docs[role]
        if 'csv_data_row_index' in ref:
            i=ref['csv_data_row_index'];check(type(i) is int and ref['csv_row_number_including_header']==i+2,'CSV index');return value[i]
        for part in ref.get('json_pointer','').split('/')[1:]:value=value[int(part)] if isinstance(value,list) else value[part.replace('~1','/').replace('~0','~')]
        return value
    check(len(inv['rows'])==101 and len(inv['historical_denominators'])==15,'denominators')
    check([r['ticker'] for r in inv['rows']]==[r['ticker'] for r in docs['wiring']['rows']],'all tickers')
    for i,row in enumerate(inv['rows']):
        check(exact(row['original_wiring_row'],deref(row['wiring_reference'])) and exact(row['observation_row'],deref(row['observation_reference'])),'original rows')
        channel=deref(row['channel_reference']);state=row['channel_state']
        for key in ('status','reasons','raw_reference','receipt_reference','volume_units_independently_certified'):check(exact(state[key],channel[key]),'channel evidence '+key)
        expected_ids=[r for r in docs['identities'] if r['ticker']==row['ticker']]
        check(exact([x['row'] for x in row['identity_matches']],expected_ids),'complete identity matches')
        for item in row['identity_matches']:
            check(exact(item['row'],deref(item['reference'])),'identity ref')
            expected=[n for n in docs['nport'] if item['row']['cusip'] and n['cusip']==item['row']['cusip']]
            check(exact([n['row'] for n in item['nport_matches']],expected),'NPORT full matches')
            for n in item['nport_matches']:
                check(exact(n['row'],deref(n['reference'])) and n['nport_reporter_is_security_issuer'] is False,'NPORT reporter')
        check(exact([r['decision'] for r in row['review_matches']],[r for r in docs['review']['decisions'] if row['ticker'] in r['tickers']]),'full review matches')
        for r in row['review_matches']:check(exact(r['decision'],deref(r['reference'])),'review reference')
    for item in inv['historical_denominators']:check(exact(item['source_row'],deref(item['reference'])),'historical original')
    for key,role in [('original_membership_scope_contract','scope'),('saved_exact_event_manifest','exact_manifest'),('saved_exact_event_rows','exact_events')]:check(exact(inv[key],docs[role]),key)
    queue=inv['extraction_queue'];check(len(queue)==53 and len(b['extraction_rows'])==53,'53 queue')
    check([q['inventory_row_index'] for q in queue]==[i for i,r in enumerate(inv['rows']) if r['raw_extraction_requested']],'complete selected queue')
    groups={}
    for i,(q,row) in enumerate(zip(queue,b['extraction_rows'])):
        check(exact(q,row['original_queue_item']) and row['queue_index']==i and row['ticker']==q['ticker'],'queue copy')
        parent=inv['rows'][q['inventory_row_index']];check(q['ticker']==parent['ticker'] and q['review_match'] in parent['review_matches'],'queue source')
        check(exact(q['identity_matches'],parent['identity_matches']),'queue all identities')
        check(row['status']=='EXTRACTED_SAVED_FACTS_NOT_IDENTITY_ADMISSION','extraction status')
        check(row['document_sha256']==q['raw_reference']['sha256'],'document mapping');groups.setdefault(row['document_sha256'],[]).append(q)
    check(set(groups)==set(b['document_references']) and b['unique_raw_extractor_call_count']==len(groups),'document set')
    totals={'documents':len(groups),'facts':0,'contexts':0,'phrases':0,'phrase_matches':0,'security_groups':0,'raw_bytes':0}
    def false_flags(value):
        for key in ('point_in_time_verified','identity_interval_verified','provider_binding_verified','risk_interval_verified','legal_training_input_admitted','promotion_allowed','execution_authorized','fit_performed','http_performed','old_audit_called','prices_recomputed','source_assertions_authenticated','full_transitive_source_closure_reverified','claimed_section_hashes_reverified','same_context_cik_title_joint_proof_created','cross_context_facts_merged','cover_cusip_identity_verified','provider_identity_verified','candidate_seal_allowed','cohort_registration_allowed','live_mutation_allowed'):
            if key in value:check(value[key] is False,'authority '+key)
    for value in [b,p,start,inv]+inv['rows']+queue+b['extraction_rows']:false_flags(value)
    for digest,items in groups.items():
        doc=json.loads(load(b['document_references'][digest]));false_flags(doc);e=doc['extraction'];false_flags(e)
        check(exact(doc['raw_references'],[q['raw_reference'] for q in items]) and exact(doc['original_review_matches'],[q['review_match'] for q in items]),'document original references')
        check(exact(e['review_decision_preserved'],doc['review_envelope']),'full review envelope')
        raw=load(items[0]['raw_reference']);check(e['raw_sha256']==digest and e['raw_byte_count']==len(raw),'raw identity')
        locator=EvidenceLocator();locator.feed(raw.decode('utf-8-sig'));locator.close()
        visible=norm(' '.join(locator.visible));check(visible==e['normalized_visible_text'] and sha(visible.encode())==e['normalized_visible_text_sha256'],'visible text/raw')
        facts=e['dei_facts'];contexts=e['contexts']
        expected_nodes=[idx for idx,n in locator.nodes.items() if n['tag'].split(':')[-1] in {'nonnumeric','nonfraction','fraction'} and (n['attrs'].get('name','') or '').split(':')[0].lower()=='dei']
        check([f['node_index'] for f in facts]==expected_nodes,'all DEI facts')
        check([c['node_index'] for c in contexts]==[idx for idx,n in locator.nodes.items() if n['tag'].split(':')[-1]=='context'],'all contexts')
        for c in contexts:check(c['context_id']==locator.nodes[c['node_index']]['attrs'].get('id') and c['text']==locator.text(c['node_index']),'context raw text')
        for f in facts:
            n=locator.nodes[f['node_index']];check(exact(f['attributes'],n['attrs']) and f['base_text']==locator.text(f['node_index']) and f['hidden']==n['hidden'],'fact raw base/attrs')
            check(f['name']==n['attrs']['name'] and f['context_ref']==n['attrs'].get('contextref'),'fact name/context')
            for c in f['continuations']:check(c['text']==locator.text(c['node_index']) and c['id']==locator.nodes[c['node_index']]['attrs'].get('id'),'continuation raw')
            check(f['resolved_text']==norm(' '.join([f['base_text']]+[c['text'] for c in f['continuations']])),'resolved fragments')
            check(f['context_match_count']==sum(c['context_id']==f['context_ref'] for c in contexts),'context links')
        for key,name in [('cik_fact_indexes','entitycentralindexkey'),('registrant_name_fact_indexes','entityregistrantname')]:check(e[key]==[i for i,f in enumerate(facts) if f['name'].split(':')[-1].lower()==name],key)
        for g in e['same_context_security_groups']:
            for field,names in [('ticker_fact_indexes',{'tradingsymbol'}),('title_fact_indexes',{'security12btitle','stocktitle','commonstocktitle'})]:check(g[field]==[i for i,f in enumerate(facts) if f['context_ref']==g['context_ref'] and f['name'].split(':')[-1].lower() in names],'class group refs')
            check(g['distinct_tickers']==sorted({facts[i]['resolved_text'] for i in g['ticker_fact_indexes']}) and g['distinct_titles']==sorted({facts[i]['resolved_text'] for i in g['title_fact_indexes']}),'group text')
        check([p['original_phrase'] for p in e['phrase_evidence']]==doc['review_envelope']['phrase_queries'],'phrases complete')
        for phrase in e['phrase_evidence']:
            query=norm(phrase['original_phrase']);check(query==phrase['normalized_phrase'],'phrase norm');positions=[];at=visible.find(query)
            while at>=0:positions.append(at);at=visible.find(query,at+1)
            check(positions==[m['offset'] for m in phrase['matches']],'all phrase offsets')
            for m in phrase['matches']:
                check(m['end_offset']==m['offset']+len(query),'phrase end');snippet=visible[max(0,m['offset']-100):m['end_offset']+100]
                check(snippet==m['snippet'] and sha(snippet.encode())==m['snippet_sha256'],'snippet hash')
            totals['phrase_matches']+=len(positions)
        totals['facts']+=len(facts);totals['contexts']+=len(contexts);totals['phrases']+=len(e['phrase_evidence']);totals['security_groups']+=len(e['same_context_security_groups']);totals['raw_bytes']+=len(raw)
    check(b['status_counts']=={'MISSING_SOURCE':0,'RAW_SHA_MISMATCH':0,'EXTRACTION_ERROR_NOT_ELIGIBLE':0,'EXTRACTED_SAVED_FACTS_NOT_IDENTITY_ADMISSION':53},'status counts')
    check({x.name for x in DIRECTORY.iterdir()}=={'started.json','batch.json','publication.json','documents'},'namespace')
    check({x.name for x in (DIRECTORY/'documents').iterdir()}=={h+'.json' for h in groups},'document files')
    totals.update(status='PASS',current_rows=101,historical_rows=15,queue_rows=53,direct_sources=len(b['source_hashes']),batch_sha256=BATCH,publication_sha256=PUBLICATION)
    return totals
if __name__=='__main__':print(json.dumps(verify(),indent=2))
