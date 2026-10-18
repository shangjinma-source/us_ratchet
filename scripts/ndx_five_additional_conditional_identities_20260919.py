"""Five bounded dated identity relations, not continuous/provider/PIT certification."""
import argparse,copy,gzip,hashlib,io,json,re,sys
from pathlib import Path
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.ndx_corrected_frontier_single_refit_archive_research import publish
BASE=ROOT/'data/cache/research'
PLAN=BASE/'latest_security_source_inventory_20260919_v1/fifteen_coordinate_plan.json'
PLAN_SHA='cac8f58e3db3278279ba8968e365911b52d06f72a5a504359e5c07b08e999d67'
COVER_BASE=ROOT/'data/cache/candidate_pools/ndx_taxonomy_v2/current_review_20260713/raw_sec'
CASES={
 'FAST':dict(cik='0000815556',cusip='311900104',company='Fastenal Company',cover_company='FASTENAL CO',title='Common stock, par value $.01 per share',period='December 31 , 2025',context='c-1',file='000081555626000009/fast-20251231.htm',sha='2b991a99593936f2f50146ca9ae4b2f537ebc946d75a1dd01077c5cd1a82fa24',memo='56481',date='April 30, 2025',ex='05/22/2025',event='May 22, 2025'),
 'ODFL':dict(cik='0000878927',cusip='679580100',company='Old Dominion Freight Line, Inc.',cover_company='OLD DOMINION FREIGHT LINE, INC.',title='Common Stock ($0.10 par value)',period='December 31 , 2025',context='C_2337f230-8703-4cd6-8aa9-0379a32d722e',file='000119312526067161/odfl-20251231.htm',sha='a822ffb8a27c0c2643475c371c78fa82bf01b34d877d3ca4fe4a1023b6c2a241',memo='54255',date='March 06, 2024',ex='03/28/2024',event='March 28, 2024'),
 'DXCM':dict(cik='0001093557',cusip='252131107',company='DexCom, Inc.',cover_company='DEXCOM, INC.',title='Common Stock, $0.001 Par Value Per Share',period='December 31 , 2025',context='c-1',file='000109355726000027/dxcm-20251231.htm',sha='29ebaafbc8b5fab0a01f8298a54291c4c41216bd5c91f318dd71b70de0c99f9e',memo='50507',date='May 27, 2022',ex='6/13/22',event='June 13, 2022'),
 'AMZN':dict(cik='0001018724',cusip='023135106',company='Amazon.com, Inc.',cover_company='AMAZON.COM, INC.',title='Common Stock, par value $.01 per share',period='December 31 , 2025',context='c-1',file='000101872426000004/amzn-20251231.htm',sha='beb1bfc28558135e76882db0cf36ba72a1ab44e2144fe37534f4da1e120ddb57',memo='50496',date='May 26, 2022',ex='6/6/22',event='June 6, 2022'),
 'LRCX':dict(cik='0000707549',cusip='512807306',company='Lam Research Corporation',cover_company='LAM RESEARCH CORPORATION',title='Common Stock, Par Value $0.001 Per Share',period='June 29 , 2025',context='c-1',file='000070754925000075/lrcx-20250629.htm',sha='10fe15913ac4380036339200474b10159c9c2d66fcce6aa66a58b63545e7178b')}
FALSE=('direct_single_document_cusip_cik_proof','latest_security_interval_verified','provider_security_binding_verified','corporate_action_completeness_verified','point_in_time_verified','promotion_allowed','legal_training_input_ready','execution_authorized','fit_performed','risk_chains_assigned','old_security_continuity_inferred')
COVER_MANIFEST_SHA=dict(FAST='c2fd88a793ee04006a2a292fa63a59723b1d7751b9ba7850d343755006bce17f',ODFL='8e6f861ede049a829aa6756bc2e9edb944c6489cfc9c108a4d29d972ce90d5a7',DXCM='18b0f01abf17aa59849ab671853cd904f9cfd888650c640eed485ab7c0923ef3',AMZN='c6c5d30a1da6e8284a88ea04361ca2faf41b70ea6cde9fe397e5512b5e7618d6',LRCX='d5fad95844973dbbc1eb765886b4911c35fb99470ee5ccd1f79e01de1fa78be4')
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),Path(publish.__code__.co_filename).resolve())}


def cover(ticker,raw):
    s=CASES[ticker];raw=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
    soup=BeautifulSoup(raw,'lxml');observed={}
    expected={'dei:entitycentralindexkey':s['cik'],'dei:entityregistrantname':s['cover_company'],'dei:tradingsymbol':ticker,'dei:security12btitle':s['title'],'dei:documentperiodenddate':s['period']}
    for field,value in expected.items():
        nodes=[n for n in soup.find_all(attrs={'name':True}) if n['name'].lower()==field]
        if len(nodes)!=1 or nodes[0].get('contextref')!=s['context'] or ' '.join(nodes[0].get_text(' ',strip=True).split())!=value:raise ValueError('Explicit same-context issuer/class cover differs: '+field)
        observed[field]=dict(original_text=nodes[0].get_text(' ',strip=True),context=nodes[0].get('contextref'))
    return observed


def relation(ticker,document_text,cover_bytes):
    s=CASES[ticker];text=' '.join(document_text.split());observed=cover(ticker,cover_bytes)
    if ticker!='LRCX':
        clauses=[f"#{s['memo']}",f"Date: {s['date']}",f"Ex-Date: {s['ex']}",f"The Ex-distribution Date is {s['event']}.",f"Effective Date:{s['event']}",f"100 {s['company']} ({ticker}) Common Shares",f"CUSIP:{s['cusip']}",'This Information Memo provides an unofficial summary']
        if any(text.count(v)!=1 for v in clauses) or re.findall(r'CUSIP:\s*([A-Z0-9]{9})',text)!=[s['cusip']]:raise ValueError('Exact common-share/CUSIP dated memo clauses required')
        evidence_kind='EXCHANGE_HOSTED_UNOFFICIAL_CLEARING_MEMO_PLUS_SEPARATE_SEC_COVER'
    else:
        clauses=['Lam Research Corporation 94-2634797','October 2, 2024 10-for-1 forward stock split 512807306 LRCX',
            "Lam Research Corporation announced a 10-for-1 forward stock split of the issuer's common stock",
            'The forward stock split became effective at 5PM Eastern Time on October 2, 2024',
            "every one (1) share of the issuer's common stock issued and outstanding at the Effective Time was automatically divided into 10 (ten) shares of common stock."]
        if any(text.count(v)!=1 for v in clauses) or '512807108' in text:raise ValueError('Exact post-action Form8937 identity clauses required')
        evidence_kind='ISSUER_FORM_8937_POST_ACTION_CUSIP_PLUS_SEPARATE_POST_ACTION_SEC_COVER'
    return dict(ticker=ticker,issuer_id='issuer:'+s['cik'],cusip=s['cusip'],conditional_research_security_id='security:'+s['cik']+':'+s['cusip'],security_class=s['title'],
        evidence_kind=evidence_kind,original_cover_fields=observed,required_original_clauses=clauses,memo_is_unofficial_summary=ticker!='LRCX',
        class_relation='EXPLICIT_CONDITIONAL_SINGLE_COMMON_CLASS_CROSS_DOCUMENT_JUDGMENT',
        company_name_relation='EXPLICIT_FIXED_CASE_AND_FASTENAL_CO_VERSUS_COMPANY_VARIATION_NOT_FUZZY_MATCH',
        corporate_action_document_contains_cik=False,corporate_action_document_ein_is_not_cik=True,
        minimum_conditional_date='2024-10-03' if ticker=='LRCX' else None,
        old_cusip_not_joined='512807108' if ticker=='LRCX' else None,
        date_role='SEPARATE_DATED_DOCUMENTS_NOT_JOINT_HISTORICAL_AVAILABILITY',
        existing_nine_panel_modified=False,**dict.fromkeys(FALSE,False))


def verify(sources):
    if any(sources.get(p)!=h for p,h in LOADED.items()):raise ValueError('Loaded code omitted')
    for p,h in sources.items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h:raise ValueError('Hard source changed: '+p)


def build():
    from pypdf import PdfReader
    sources=dict(LOADED)
    def read(path,h):
        p=Path(path).resolve();raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=h:raise ValueError('Actual raw evidence differs')
        if str(p) in sources and sources[str(p)]!=h:raise ValueError('Source conflict')
        sources[str(p)]=h;return raw
    plan=json.loads(read(PLAN,PLAN_SHA));rows=[]
    for t,s in CASES.items():
        row,=[r for r in plan['rows'] if r['ticker']==t];wrapped,=row['action_document_facts'];fact=wrapped['fact']
        if fact['cusip']!=s['cusip'] or row['current_issuer_id']!='issuer:'+s['cik']:raise ValueError('Plan coordinates differ')
        doc=fact['identity_evidence'] if t=='LRCX' else fact
        raw=read(doc['raw_path'],doc['raw_sha256']);pdf=PdfReader(io.BytesIO(raw));text='\n'.join(p.extract_text() for p in pdf.pages)
        p=COVER_BASE/('issuer_'+s['cik'])/s['file'];cover_raw=read(p,s['sha'])
        cover_metadata=json.loads(read(str(p)+'.manifest.json',COVER_MANIFEST_SHA[t]))
        if cover_metadata['content_sha256']!=s['sha'] or cover_metadata['cik']!=s['cik']:raise ValueError('Original cover manifest binding differs')
        value=relation(t,text,cover_raw)
        value.update(original_action_fact=copy.deepcopy(fact),corporate_action_raw=dict(path=doc['raw_path'],sha256=doc['raw_sha256']),
            original_cover=dict(path=str(p),sha256=s['sha']),corporate_action_received_at_utc=doc['received_at_utc'],corporate_action_source_url=doc.get('source_url'),source_url_not_present_in_prior_fact='source_url' not in doc,
            original_cover_capture_metadata=cover_metadata,cover_manifest_availability_date_independently_verified=False,
            all_document_dates_retained_separately=True)
        if t=='LRCX':
            announcement=read(fact['raw_path'],fact['raw_sha256']);announcement_text=' '.join(BeautifulSoup(announcement,'html.parser').get_text(' ',strip=True).split())
            clause="Lam Research's common stock will begin trading on a post-split basis at the market open on Thursday, October 3, 2024"
            if announcement_text.count(clause)!=1:raise ValueError('Actual issuer first adjusted trading date required')
            value['first_post_action_trading_date']=fact['first_adjusted_trading_date']
            if value['first_post_action_trading_date']!='2024-10-03':raise ValueError('No pre-transition LRCX coordinate admitted')
        rows.append(value)
    verify(sources)
    return dict(schema='FIVE_ADDITIONAL_DATED_CONDITIONAL_IDENTITIES_V1',rows=rows,security_count=5,source_hashes=sources,
        source_scope='DIRECT_RAW_COVER_AND_ACTION_BYTES_PLUS_HARD_PRIOR_PLAN_NOT_RECURSIVE_HISTORICAL_PROVENANCE',existing_nine_panel_modified=False,**dict.fromkeys(FALSE,False))


def publish_verified(path,value):
    verify(value['source_hashes']);saved=publish(path,value);verify(value['source_hashes']);return saved


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();print(json.dumps(publish_verified(a.output,build())))
