"""Validate explicit research selections against already extracted JSON, never parse filings."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CONTRACT=ROOT/'research_contracts/full_pool_security_group_selection_20261002_v1.json'
CONTRACT_SHA='611eda9d6e476bd0909256bf7fcffbecb9ddcb0ecdf4ece09d06b06d0eacad9e'
FALSE=('point_in_time_verified','identity_interval_verified','promotion_allowed','legal_training_input_admitted')

def require(ok,message):
    if not ok:raise ValueError(message)

def validate_selection(row,queue_item,document,document_reference):
    require(all(row[k] is False for k in FALSE),'Selection authority changed')
    require(row['ticker']==queue_item['ticker'] and type(row['inventory_row_index']) is int and row['inventory_row_index']==queue_item['inventory_row_index'],'Queue identity differs')
    require(row['raw_sha256']==queue_item['raw_reference']['sha256']==document['raw_sha256'] and row['document_reference']==document_reference,'Raw/document binding differs')
    e=document['extraction'];groups=e['same_context_security_groups'];facts=e['dei_facts']
    require(row['all_security_groups']==groups,'Unselected alternatives lost')
    indexes=row['selected_group_indexes']
    if row['status']=='UNRESOLVED_EXPLICIT_SELECTION_REQUIRED':
        require(indexes==[] and all(row[k] is None for k in ('selected_title_fact_index','context_ref','exact_title','selected_group_pointer','selected_title_fact_pointer')) and bool(row['selection_reason']),'Unresolved must preserve null selection')
    else:
        require(row['status']=='EXPLICIT_CONDITIONAL_CLASS_SELECTION_NOT_IDENTITY_CERTIFICATION' and len(indexes)==1 and type(indexes[0]) is int and 0<=indexes[0]<len(groups),'Explicit group index required')
        i=indexes[0];g=groups[i];j=row['selected_title_fact_index']
        require(type(j) is int and 0<=j<len(facts) and all(type(v) is int for v in g['title_fact_indexes']) and g['title_fact_indexes']==[j] and g['distinct_tickers']==[row['ticker']] and g['distinct_titles']==[row['exact_title']],'Selected class differs')
        f=facts[j]
        require(f['name']=='dei:Security12bTitle' and f['resolved_text']==row['exact_title'] and f['context_ref']==row['context_ref']==g['context_ref'] and f['continuation_complete'] is True and type(f['context_match_count']) is int and f['context_match_count']==1,'Title fact/context differs')
        require(row['selected_group_pointer']=='/extraction/same_context_security_groups/'+str(i) and row['selected_title_fact_pointer']=='/extraction/dei_facts/'+str(j),'Fact pointer differs')
        require(sum(x['context_id']==row['context_ref'] for x in e['contexts'])==1,'Context must resolve exactly once')
        require(type(g['ticker_fact_indexes']) is list and len(g['ticker_fact_indexes'])>0 and all(type(k) is int and 0<=k<len(facts) for k in g['ticker_fact_indexes']),'Exact nonempty ticker fact indexes required')
        for k in g['ticker_fact_indexes']:
            tf=facts[k];require(tf['name']=='dei:TradingSymbol' and tf['resolved_text']==row['ticker'] and tf['context_ref']==row['context_ref'],'Ticker fact differs')
        if row['ticker']=='MSFT':require(row['exact_title']=='Common stock, $ 0.00000625 par value per share' and row['selection_reason']=='EXPLICIT_COMMON_STOCK_NOT_TWO_NOTES_GROUPS','MSFT notes cannot replace common stock')
    rev=queue_item['review_match']['decision'];a=row['supporting_evidence']
    require(a['early_window_review_availability_verified'] is False and type(a['review_selection_postdates_window_start']) is bool,'Availability flags must be exact bool')
    require(a=={'review_reference':queue_item['review_match']['reference'],'selection_date':rev['selection_date'],'evidence_available_date':rev['evidence_available_date'],'effective_from':rev['effective_from'],'review_selection_postdates_window_start':rev['selection_date']>'2026-03-20','early_window_review_availability_verified':False,'local_first_available_at':None},'Availability assertions differ')
    s=row['class_handling']
    if row['ticker']=='PDD':require(type(s['ordinary_shares_per_ads']) is int and s['holdings_conversion_performed'] is False and s['price_conversion_performed'] is False and s=={'kind':'ADS_TITLE_PRESERVED_NO_ORDINARY_CONVERSION','ordinary_shares_per_ads':4,'holdings_conversion_performed':False,'price_conversion_performed':False} and 'representing four Class A ordinary shares' in row['exact_title'],'ADS contract differs')
    elif row['ticker']=='ASML':
        require(s['kind']=='ORDINARY_TO_NEW_YORK_SHARES_CROSS_DOCUMENT_CONDITIONAL_ASSUMPTION' and s['annual_registered_class']==row['exact_title']=='Ordinary Shares' and s['conditional_security_class']=='New York Shares' and s['new_window_class_identity_verified'] is False and set(s['source_references'])=={'identity.json','publication.json'},'ASML cross-document assumption differs')
    else:require(s is None,'Unexpected class conversion')
    return deepcopy(row)

def read_contract():
    require(hashlib.sha256(SOURCE.read_bytes()).hexdigest()==LOADED_SHA,'Loaded verifier changed')
    raw=CONTRACT.read_bytes();require(hashlib.sha256(raw).hexdigest()==CONTRACT_SHA,'Reviewed contract changed')
    doc=json.loads(raw);require(doc['schema']=='SAVED_SEC_CONDITIONAL_SELECTION_CONTRACT_V1' and type(doc['row_count']) is int and doc['row_count']==len(doc['rows'])==53 and len({r['ticker'] for r in doc['rows']})==53 and all(doc[k] is False for k in FALSE),'Full contract differs')
    return doc
