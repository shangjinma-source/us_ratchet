"""Pure, non-executable investment-review proposals. Never writes or quotes orders."""
from datetime import datetime
from fractions import Fraction
from hashlib import sha256

ACTIONS = {'KEEP','PAUSE_BUY','REDUCE_BUY','REDUCE_HOLDING','EXIT','ABSTAIN'}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def moment(value):
    result = datetime.fromisoformat(value.replace('Z','+00:00'))
    require(result.tzinfo is not None, 'AWARE_TIMESTAMP_REQUIRED')
    return result


def integer(value):
    require(type(value) is int and value >= 0, 'NONNEGATIVE_INTEGER_REQUIRED')
    return value


def fraction(value):
    require(isinstance(value,str), 'FRACTION_STRING_REQUIRED')
    result=Fraction(value)
    require(0 <= result <= 1, 'FRACTION_OUT_OF_RANGE')
    return result


def build_review_proposal(*, review, original_preview, account, sources, now):
    """Accept fresh server-owned preview/account and a source-bound review.

    original_preview must expose effective_target_quantities and its risk validity
    interval. sources is a mapping of ids to full source text and metadata.
    Source binding proves quoted evidence, not economic correctness or adoption.
    """
    current=moment(now)
    require(review.get('schema')=='NEWS_INVESTMENT_REVIEW_V1','REVIEW_SCHEMA_REQUIRED')
    require(original_preview.get('status') in ('READY','HOLD'),'FRESH_ORIGINAL_PREVIEW_REQUIRED')
    binding={key:original_preview[key] for key in ('account_revision','target_id','proposal_id')}
    require(all(isinstance(v,str) and v for v in binding.values()),'ORIGINAL_BINDING_REQUIRED')
    require(binding['account_revision']==account['revision'],'STALE_ACCOUNT')
    require(all(review.get(k)==v for k,v in binding.items()),'STALE_REVIEW_BINDING')
    require(moment(original_preview['risk_valid_from']) <= current < moment(original_preview['risk_valid_until']), 'ORIGINAL_RISK_EXPIRED')
    created,expiry=moment(review['created_at']),moment(review['valid_until'])
    require(created <= current < expiry,'REVIEW_EXPIRED_OR_FUTURE')
    require(isinstance(review.get('review_id'),str) and review['review_id'],'REVIEW_ID_REQUIRED')
    require(account.get('cash_confirmation_valid') is True,'CASH_CONFIRMATION_REQUIRED')
    cash=Fraction(str(account['available_cash']))
    require(cash>=0,'NEGATIVE_AVAILABLE_CASH')
    base=dict(schema='NEWS_INVESTMENT_REVIEW_PROPOSAL_V1',status='REVIEW_PROPOSAL_ONLY',
        original_binding=binding,review_id=review['review_id'],review_created_at=review['created_at'],
        review_valid_until=review['valid_until'],generated_at=now,rows=[],orders_created=False,
        executable=False,requires_fresh_execution_validation=True,
        limitation='Evidence-bound AI opinion, not validated investment alpha or executable orders.')
    require(isinstance(account.get('orders'),dict),'OPEN_ORDER_STATE_REQUIRED')
    require(all(o.get('status') in ('OPEN','FILLED','CANCELLED','CANCELED','REJECTED','EXPIRED') for o in account['orders'].values()),'ORDER_STATUS_UNKNOWN')
    if any(o['status']=='OPEN' for o in account['orders'].values()):
        return dict(base,status='WAIT_RECONCILIATION',reason='EXISTING_OPEN_ORDERS')
    held=account['shares'];target=original_preview['effective_target_quantities']
    require(isinstance(held,dict) and isinstance(target,dict),'TARGET_AND_HOLDINGS_REQUIRED')
    for quantity in list(held.values())+list(target.values()):integer(quantity)
    domain={sid for sid in set(held)|set(target) if held.get(sid,0)>0 or target.get(sid,0)>0}
    rows=review['rows']
    require(isinstance(rows,list) and len(rows)==len(domain) and {r['security_id'] for r in rows}==domain,'EXACT_REVIEW_DOMAIN_REQUIRED')
    for row in rows:
        sid=row['security_id'];action=row['action'];quantity=held.get(sid,0);original=target.get(sid,0)
        require(action in ACTIONS,'ACTION_NOT_ALLOWED')
        require(isinstance(row.get('reason'),str) and row['reason'].strip(),'REASON_REQUIRED')
        for field in ('counterevidence','uncertainty'):
            require(isinstance(row.get(field,[]),list) and all(isinstance(value,str) for value in row.get(field,[])), 'REVIEW_EXPLANATION_LIST_REQUIRED')
        evidence=row.get('evidence')
        require(isinstance(evidence,list),'EVIDENCE_LIST_REQUIRED')
        require(action=='ABSTAIN' or bool(evidence),'EVIDENCE_REQUIRED')
        verified=[]
        for item in evidence:
            source=sources[item['source_id']]
            require(source.get('content_kind')=='FULL_TEXT','FULL_SOURCE_REQUIRED')
            require(sid in source['security_ids'],'SOURCE_SECURITY_MISMATCH')
            require(sha256(source['text'].encode('utf-8')).hexdigest()==source['text_sha256'],'SOURCE_TEXT_HASH_MISMATCH')
            require(item.get('source_sha256')==source['text_sha256'],'REVIEW_SOURCE_HASH_MISMATCH')
            require(isinstance(item.get('quote'),str) and item['quote'].strip() and item['quote'] in source['text'],'EXACT_QUOTE_REQUIRED')
            published,observed=moment(source['published_at']),moment(source['observed_at'])
            require(published<=observed<=created,'SOURCE_NOT_AVAILABLE_AT_REVIEW')
            verified.append(dict(source_id=item['source_id'],source_sha256=source['text_sha256'],
                quote=item['quote'],source_url=source.get('url'),published_at=source['published_at'],observed_at=source['observed_at']))
        desired=original
        if action=='PAUSE_BUY':desired=min(original,quantity)
        elif action=='REDUCE_BUY':desired=min(original,quantity+int(max(original-quantity,0)*fraction(row['buy_fraction'])))
        elif action=='REDUCE_HOLDING':desired=min(original,int(quantity*fraction(row['holding_fraction'])))
        elif action=='EXIT':desired=0
        require(desired<=original,'ORIGINAL_SELL_MUST_NOT_BE_REDUCED')
        base['rows'].append(dict(security_id=sid,action=action,reason=row['reason'],evidence=verified,
            counterevidence=list(row.get('counterevidence',[])),uncertainty=list(row.get('uncertainty',[])),
            held_quantity=quantity,original_target_quantity=original,proposed_target_quantity=desired,
            proposed_delta=desired-quantity,reviewed=action!='ABSTAIN'))
    return base
