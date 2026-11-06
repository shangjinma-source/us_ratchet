"""Exact XEL witness-to-official-cash bridge; research only, no gate waiver."""
from pathlib import Path
from hashlib import sha256
import json,gzip
from copy import deepcopy
from fractions import Fraction
ROOT=Path(__file__).resolve().parents[2]
REVIEW='tmp/rsi2_xel_review_20261106/review_rows.json'
REVIEW_SHA='2b7c4d9ba6a8465271a5919a00c5b8a2ce9ad9024a1802d77adf370f1fd34588'
SID='research:security:xel'
DAY='2021-06-14'
def require(condition,reason):
    if not condition:raise ValueError(reason)
def checked(name,digest):
    raw=(ROOT/name).read_bytes();require(sha256(raw).hexdigest()==digest,'SOURCE_HASH_MISMATCH:'+name);return raw
def map_event(event):
    review=json.loads(checked(REVIEW,REVIEW_SHA))['review_rows']
    require(len(review)==1,'SINGLE_REVIEW_REQUIRED');row=review[0]
    require((row['security_id'],row['ex_date'],row['payment_date'],row['currency'])==(SID,DAY,'2021-07-20','USD'),'OFFICIAL_IDENTITY_DATE_CURRENCY_MISMATCH')
    require(Fraction(row['amount_per_share'])==Fraction(183,400),'OFFICIAL_AMOUNT_MISMATCH')
    require(row['official_history_row']=={'Code':None,'Currency':'USD','DeclaredDate':'05/19/2021 00:00:00','DividendAmount':0.4575,'ExDate':'06/14/2021 00:00:00','PayDate':'07/20/2021 00:00:00','PaymentFrequency':'Quarterly','RecordDate':'06/15/2021 00:00:00','Type':'OrdinaryDividend'},'OFFICIAL_HISTORY_ROW_MISMATCH')
    sources={name:checked(name,digest) for name,digest in row['source_sha256'].items()}
    require(set(row['source_references'])==set(sources),'SOURCE_REFERENCE_MISMATCH')
    witnesses=row['observed_provider_events'];require(len(witnesses)==1,'SINGLE_PROVIDER_WITNESS_REQUIRED');witness=witnesses[0]
    for key in ('ticker','security_id','date','kind','provider_event','source','source_sha256'):
        require(event.get(key)==witness[key],'EVENT_WITNESS_MISMATCH:'+key)
    require(event['security_id']==SID and event['date']==DAY and event['kind']=='dividends','EVENT_SCOPE_MISMATCH')
    require(event['provider_event']=={'amount':0.458,'date':1623677400},'PROVIDER_PAYLOAD_MISMATCH')
    raw=sources[event['source']];chart=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)['chart']['result'][0]
    require(chart.get('meta',{}).get('symbol')=='XEL','PROVIDER_SYMBOL_MISMATCH')
    provider=[v for v in chart.get('events',{}).get('dividends',{}).values() if v.get('date')==1623677400]
    require(provider==[event['provider_event']],'PROVIDER_BYTES_EVENT_MISMATCH')
    return {'event_id':'residual-xel-exact-gross:2021-06-14','security_id':SID,'ex_date':DAY,'payment_date':'2021-07-20','amount_per_share':'183/400','currency':'USD','withholding_rate':'0','provider_event':deepcopy(event['provider_event']),'source_hashes':{REVIEW:REVIEW_SHA,**row['source_sha256']},'evidence_scope':'EXACT_OFFICIAL_OVERRIDE_OF_THIS_ROUNDED_PROVIDER_WITNESS_ONLY','limitation':row['limitation']}
