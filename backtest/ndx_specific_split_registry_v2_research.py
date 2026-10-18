"""Explicit 25-event research registry; two identity transitions remain unusable."""
import gzip,hashlib,json
from io import BytesIO
from pathlib import Path
from bs4 import BeautifulSoup
from backtest import ndx_nominal_quote_reconstruction_research as nominal
from scripts import ndx_standard_split_fact_readback_research as original
ROOT=Path(__file__).resolve().parents[1]
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),Path(original.__file__).resolve(),nominal.SOURCE)}
OLD_PATH=ROOT/'data/cache/research/standard_split_official_evidence_20260912_v1/specific_split_fact_readback.json'
OLD_SHA='f421d8b95c6542139b016a853c3ab9e7f69d76daaff79e4592918fce8e8e4d55'
ALL_PATH=ROOT/'data/cache/research/remaining_standard_split_evidence_20260912_v1/all_32_event_status.json'
ALL_SHA='99119e5c3664b272d65eec498fb18714feb4fa7aa43e0ceff9682c79df8cafae'
BLOCKED=frozenset({'EXC','CMCSA','HON','ILMN','AZN','SIRI'})
TRANSITIONS=frozenset({'LCID','LRCX'})
MANIFESTS={
 'alphabet':('root_return_semantics_probe_20260912_v1/goog_split_primary_manifest_20260912.json','38775521ad3e8338760b1f385cffa1b2462180030bdafb782eadf5f83b0ef474'),
 'nvda':('incumbent_price_source_probe_20260912_v1/nvda_official_manifest_20260912.json','1e1b411f19165c50ce816f7b7c2238bedae5315767c7d977152ae5dfc0fac839'),
 'avgo':('preference_price_action_source_probe_20260912_v1/manifest.json','fac4d6e47a266d69891a9415919d0a3cfbad639c0e3d7bc111a2a15ab30e32f7'),
 'ftnt':('standard_split_registry_20260912_v2/ftnt_manifest.json','b768a2b4a563ca910a2d3464b322d437d41f178cf603dd4573d8fd88f263613d')}

def merge_source(sources,path,digest):
    path=str(Path(path).resolve())
    if path in sources and sources[path]!=digest:raise ValueError('Conflicting registry source')
    sources[path]=digest

def require(text,clauses):
    for clause in clauses:
        if clause not in text:raise ValueError('Required exact split declaration differs: '+clause)

def load_registry():
    from pypdf import PdfReader
    sources=dict(LOADED);nominal.verify(sources)
    def load(path,digest):
        merge_source(sources,path,digest);nominal.verify({str(Path(path).resolve()):digest})
        value=json.loads(Path(path).read_bytes(),object_pairs_hook=nominal._unique_pairs)
        for p,h in value.get('source_hashes',{}).items():merge_source(sources,p,h)
        return value
    old=load(OLD_PATH,OLD_SHA);all_events=load(ALL_PATH,ALL_SHA)
    if (old['specific_event_count']!=9 or all_events['returned_event_count']!=32 or
        old['point_in_time_verified'] is not False or all_events['point_in_time_verified'] is not False):raise ValueError('Unexpected evidence contract')
    facts=[dict(x) for x in old['specific_events']+all_events['specific_new_events']]
    captures={}
    for family,(relative,digest) in MANIFESTS.items():
        manifest=load(ROOT/'data/cache/research'/relative,digest)
        for c in manifest.get('probes',manifest.get('captures',[])):
            captures[c['name']]=c
            path=c.get('response_path',c.get('raw_path'));h=c.get('response_sha256',c.get('raw_sha256'))
            if path:merge_source(sources,path,h)
    nominal.verify(sources)
    def document(name):
        c=captures[name]
        if c.get('http_status')!=200:raise ValueError('Required primary evidence not captured')
        path=c.get('response_path',c.get('raw_path'));raw=Path(path).read_bytes()
        raw=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
        text=' '.join(page.extract_text() for page in PdfReader(BytesIO(raw)).pages) if raw.startswith(b'%PDF') else BeautifulSoup(raw,'html.parser').get_text(' ',strip=True)
        text=' '.join(text.split()).replace('\u2010','-')
        return text,dict(raw_path=path,raw_sha256=c.get('response_sha256',c.get('raw_sha256')),
          received_at_utc=c.get('received_at_utc'),source_url=c.get('request_url',c.get('request',{}).get('url')),
          decoded_sha256=hashlib.sha256(raw).hexdigest())
    text,ref=document('sec_goog_split_approved_2022')
    require(text,['Class A Common Stock, $0.001 par value GOOGL','Class C Capital Stock, $0.001 par value GOOG',
      '19 additional shares for every one share held','Trading is expected to begin on a split-adjusted basis on July 18, 2022.'])
    executed,executed_ref=document('sec_goog_split_executed_2022')
    require(executed,['On July 15, 2022, the company executed a 20-for-one stock split','Class A, Class B, and Class C stock'])
    for ticker,security_class in [('GOOG','CLASS_C_CAPITAL'),('GOOGL','CLASS_A_COMMON')]:
        facts.append(dict(ticker=ticker,first_adjusted_trading_date='2022-07-18',new_shares=20,old_shares=1,
          security_class=security_class,cusip=None,issuer_cik='0001652044',specific_simple_share_split_event_supported=True,
          first_trading_date_declaration='EXPECTED_IN_APPROVED_8K',actual_execution_date_separately_reported='2022-07-15',
          source_reference=ref,execution_evidence=executed_ref))
    for ticker,name,day,clauses in [
      ('NVDA','nvda_official_split_faq','2024-06-10',['nine additional shares of common stock','Trading is expected to commence on a split- adjusted basis at market open on Monday, June 10, 2024.']),
      ('AVGO','avgo_official_20240612_split_faq','2024-07-15',['an additional nine shares of Broadcom common stock for every one share of Broadcom common stock held.',
       'Trading is expected to commence on a split-adjusted basis when the Nasdaq Stock Market opens on July 15, 2024.'])]:
        text,ref=document(name);require(text,clauses)
        facts.append(dict(ticker=ticker,first_adjusted_trading_date=day,new_shares=10,old_shares=1,security_class='COMMON',
          cusip=None,specific_simple_share_split_event_supported=True,source_reference=ref,first_trading_date_declaration='EXPECTED_IN_ISSUER_FAQ'))
    text,ref=document('ftnt_occ50626_miax')
    fact=original.parse_occ(text,ticker='FTNT',session='2022-06-23',new_shares=5,old_shares=1,cusip='34959E109')
    fact.update(source_reference=ref,specific_simple_share_split_event_supported=True,security_class='COMMON');facts.append(fact)
    if len(facts)!=25 or len({(x['ticker'],x['first_adjusted_trading_date']) for x in facts})!=25:raise ValueError('Exact 25-event denominator required')
    blocked={x['ticker'] for x in all_events['simple_split_interface_blocklist']}
    if blocked!=BLOCKED:raise ValueError('Complex-action blocklist differs')
    for fact in facts:
        if fact['ticker'] in BLOCKED:raise ValueError('Complex event entered registry')
        transition=fact.get('identity_transition_requires_explicit_mapping',False)
        if (fact['ticker'] in TRANSITIONS)!=transition:raise ValueError('Identity-transition requirement differs')
        fact['simple_split_guard_eligible']=not transition
    nominal.verify(sources)
    return dict(schema='EXPLICIT_25_SPECIFIC_SPLIT_EVENT_REGISTRY_V2',events=sorted(facts,key=lambda x:(x['ticker'],x['first_adjusted_trading_date'])),
      source_hashes=sources,event_count=25,guard_eligible_event_count=23,blocked_tickers=sorted(BLOCKED),identity_transition_blocked_tickers=sorted(TRANSITIONS),
      corporate_action_completeness_verified=False,price_identity_verified=False,point_in_time_verified=False,promotion_allowed=False,
      old_ftnt_8k_lacks_first_adjusted_day_new_memo_used=True)
