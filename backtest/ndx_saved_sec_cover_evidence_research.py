"""Bounded, untrusted saved-HTML evidence extraction; no identity certification."""
from copy import deepcopy
import hashlib
from html.parser import HTMLParser
import json
import re

MAX_RAW_BYTES = 32_000_000
MAX_NODES = 250000
MAX_DEPTH = 256
MAX_FACTS = 10000
VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
SCHEMA = 'SAVED_SEC_COVER_EVIDENCE_RESEARCH_V1'


def require(ok, message):
    if not ok: raise ValueError(message)


def sha(raw): return hashlib.sha256(raw).hexdigest()
def normalize(text): return re.sub(r'\s+', ' ', text).strip()
def local(tag): return tag.split(':')[-1].lower()


class Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.nodes=[{'tag':'ROOT','attrs':{},'children':[],'parent':None}]
        self.stack=[0]; self.issues=[]

    def handle_starttag(self, tag, attrs):
        require(len(self.nodes)<MAX_NODES and len(self.stack)<MAX_DEPTH,'HTML resource bound exceeded')
        index=len(self.nodes)
        duplicates=[key for key,_ in attrs if sum(k==key for k,_ in attrs)>1]
        if duplicates: self.issues.append({'kind':'DUPLICATE_ATTRIBUTES','node_index':index,'names':sorted(set(duplicates))})
        self.nodes.append({'tag':tag,'attrs':dict(attrs),'attribute_pairs':attrs,'children':[],'parent':self.stack[-1]})
        self.nodes[self.stack[-1]]['children'].append(index)
        if local(tag) not in VOID: self.stack.append(index)

    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if self.stack[-1] != 0 and self.nodes[self.stack[-1]]['tag']==tag: self.stack.pop()

    def handle_endtag(self,tag):
        for index in range(len(self.stack)-1,0,-1):
            if self.nodes[self.stack[index]]['tag']==tag:
                del self.stack[index:]; return

    def handle_data(self,text): self.nodes[self.stack[-1]]['children'].append(text)

    def text(self,index,visible=False):
        node=self.nodes[index]; tag=local(node['tag']); attrs=node['attrs']
        if tag=='exclude' and not visible: return ''
        if visible and (tag in {'script','style','hidden'} or 'hidden' in attrs or
            re.search(r'(display\s*:\s*none|visibility\s*:\s*hidden)',attrs.get('style','') or '',re.I)):
            return ''
        return ' '.join(self.text(child,visible) if type(child) is int else child for child in node['children'])

    def descendants(self,index):
        result=[]; pending=[index]
        while pending:
            node=pending.pop(); result.append(node)
            pending.extend(reversed([child for child in self.nodes[node]['children'] if type(child) is int]))
        return result

    def hidden(self,index):
        while index is not None:
            node=self.nodes[index]; attrs=node['attrs']
            if local(node['tag'])=='hidden' or 'hidden' in attrs or re.search(r'display\s*:\s*none|visibility\s*:\s*hidden',attrs.get('style','') or '',re.I): return True
            index=node['parent']
        return False


def extract_saved_sec_evidence(raw_bytes, source_reference, review_decision):
    require(type(raw_bytes) is bytes and 0<len(raw_bytes)<=MAX_RAW_BYTES,'Bounded raw bytes required')
    require(type(source_reference) is dict and set(source_reference)=={'path','sha256'} and
            type(source_reference['path']) is str and bool(source_reference['path'].strip()),'Source reference schema')
    digest=sha(raw_bytes)
    require(source_reference['sha256']==digest,'Raw source reference mismatch')
    require(type(review_decision) is dict and review_decision.get('expected_raw_sha256')==digest,'Review expected raw SHA mismatch')
    # JSON-only evidence, retained verbatim as data; no review instructions execute.
    json.dumps(review_decision,allow_nan=False)
    phrases=review_decision.get('phrase_queries',[])
    require(type(phrases) is list and len(phrases)<=100 and all(type(p) is str and 0<len(p)<=2000 and normalize(p) for p in phrases),'Bounded phrase queries required')
    parser=Parser(); parser.feed(raw_bytes.decode('utf-8-sig')); parser.close()
    issues=list(parser.issues); ids={}
    for index,node in enumerate(parser.nodes):
        if node['attrs'].get('id'): ids.setdefault(node['attrs']['id'],[]).append(index)
    for identity, indexes in ids.items():
        if len(indexes)>1: issues.append({'kind':'DUPLICATE_NODE_ID','id':identity,'node_indexes':indexes})
    contexts=[]
    for index,node in enumerate(parser.nodes):
        if local(node['tag'])!='context': continue
        identifiers=[]; periods=[]; dimensions=[]
        for child in parser.descendants(index):
            item=parser.nodes[child]; tag=local(item['tag'])
            if tag=='identifier': identifiers.append({'scheme':item['attrs'].get('scheme'),'value':normalize(parser.text(child))})
            elif tag in {'startdate','enddate','instant','forever'}: periods.append({'kind':tag,'value':normalize(parser.text(child))})
            elif tag in {'explicitmember','typedmember'}: dimensions.append({'kind':tag,'dimension':item['attrs'].get('dimension'),
                'value':normalize(parser.text(child)),'node_attributes':deepcopy(item['attrs'])})
        contexts.append({'node_index':index,'context_id':node['attrs'].get('id'),
            'identifiers':identifiers,'periods':periods,'dimensions':dimensions,'text':normalize(parser.text(index))})
    facts=[]
    for index,node in enumerate(parser.nodes):
        name=node['attrs'].get('name','') or ''
        if local(node['tag']) not in {'nonnumeric','nonfraction','fraction'} or name.split(':')[0].lower()!='dei': continue
        require(len(facts)<MAX_FACTS,'Fact resource bound exceeded')
        fragments=[normalize(parser.text(index))]; continuation=[]; seen=set(); next_id=node['attrs'].get('continuedat')
        complete=True
        while next_id:
            require(len(continuation)<256,'Continuation resource bound exceeded')
            if next_id in seen or len(ids.get(next_id,[]))!=1:
                issues.append({'kind':'BROKEN_OR_AMBIGUOUS_CONTINUATION','fact_node_index':index,'continuation_id':next_id}); complete=False; break
            seen.add(next_id); target=ids[next_id][0]; target_node=parser.nodes[target]
            if local(target_node['tag'])!='continuation':
                issues.append({'kind':'CONTINUATION_WRONG_NODE_TYPE','fact_node_index':index,'continuation_id':next_id}); complete=False; break
            fragment=normalize(parser.text(target)); fragments.append(fragment)
            continuation.append({'id':next_id,'node_index':target,'text':fragment,'hidden':parser.hidden(target)})
            next_id=target_node['attrs'].get('continuedat')
        context_ref=node['attrs'].get('contextref')
        matching=[c for c in contexts if c['context_id']==context_ref]
        if len(matching)!=1: issues.append({'kind':'MISSING_OR_AMBIGUOUS_CONTEXT','fact_node_index':index,'context_ref':context_ref})
        facts.append({'node_index':index,'name':name,'context_ref':context_ref,'id':node['attrs'].get('id'),
            'hidden':parser.hidden(index),'continued_at':node['attrs'].get('continuedat'),
            'attributes':deepcopy(node['attrs']),'base_text':fragments[0],
            'continuations':continuation,'resolved_text':normalize(' '.join(fragments)),
            'continuation_complete':complete,'context_match_count':len(matching)})
    groups=[]
    for context_ref in dict.fromkeys(fact['context_ref'] for fact in facts):
        members=[i for i,f in enumerate(facts) if f['context_ref']==context_ref]
        tickers=[i for i in members if facts[i]['name'].split(':')[-1].lower()=='tradingsymbol']
        titles=[i for i in members if facts[i]['name'].split(':')[-1].lower() in {'security12btitle','stocktitle','commonstocktitle'}]
        if tickers or titles:
            distinct_tickers=sorted(set(facts[i]['resolved_text'] for i in tickers))
            distinct_titles=sorted(set(facts[i]['resolved_text'] for i in titles))
            groups.append({'context_ref':context_ref,'ticker_fact_indexes':tickers,'title_fact_indexes':titles,
                'distinct_tickers':distinct_tickers,'distinct_titles':distinct_titles,
                'missing_ticker':not tickers,'missing_title':not titles,
                'multiple_tickers_or_classes_unresolved':len(distinct_tickers)>1 or len(distinct_titles)>1})
    visible=normalize(parser.text(0,True)); phrase_evidence=[]
    for phrase in phrases:
        query=normalize(phrase); positions=[]; start=0
        while True:
            position=visible.find(query,start)
            if position<0: break
            require(len(positions)<10000,'Phrase match bound exceeded')
            snippet=visible[max(0,position-100):min(len(visible),position+len(query)+100)]
            positions.append({'offset':position,'end_offset':position+len(query),'snippet':snippet,'snippet_sha256':sha(snippet.encode())})
            start=position+1
        phrase_evidence.append({'original_phrase':phrase,'normalized_phrase':query,'matches':positions})
    return {'schema':SCHEMA,'source_reference':deepcopy(source_reference),'raw_sha256':digest,
        'raw_byte_count':len(raw_bytes),'decoding':'UTF-8-SIG_STRICT_NO_REPLACEMENT',
        'phrase_offset_domain':'NORMALIZED_VISIBLE_TEXT_CODEPOINT_OFFSETS_NOT_RAW_BYTES',
        'missing_cik_fact':not any(f['name'].split(':')[-1].lower()=='entitycentralindexkey' for f in facts),
        'missing_security_title_fact':not any(group['title_fact_indexes'] for group in groups),
        'review_decision_preserved':deepcopy(review_decision),
        'contexts':contexts,'dei_facts':facts,'same_context_security_groups':groups,'issues':issues,
        'cik_fact_indexes':[i for i,f in enumerate(facts) if f['name'].split(':')[-1].lower()=='entitycentralindexkey'],
        'registrant_name_fact_indexes':[i for i,f in enumerate(facts) if f['name'].split(':')[-1].lower()=='entityregistrantname'],
        'normalized_visible_text':visible,'normalized_visible_text_sha256':sha(visible.encode()),'phrase_evidence':phrase_evidence,
        'visible_text_semantics':'HTML_TEXT_EXCLUDING_SCRIPT_STYLE_HIDDEN_NO_BROWSER_CSS_RENDERING',
        'review_risk_semantics':'PRESERVED_LATE_SAVED_REVIEW_NOT_RECLASSIFIED_OR_EARLY_AVAILABILITY_PROOF',
        'same_context_cik_title_joint_proof_created':False,'cross_context_facts_merged':False,
        'claimed_section_hashes_reverified':False,'cover_cusip_identity_verified':False,
        'provider_identity_verified':False,'point_in_time_verified':False,'promotion_allowed':False,
        'candidate_seal_allowed':False,'cohort_registration_allowed':False,'live_mutation_allowed':False}
