"""Unattached content-only split timing review; no account schema migration."""
from pathlib import Path
from hashlib import sha256
from core.strategy_account_ledger import canonical, require
from core.strategy_account_split_v1 import moment
from data.strategy_recorded_split_review_v1 import review_recorded_splits as legacy

SOURCE_HASH='c573bf38df7e612d751028c9367ceeb9b6348f60e7e15c8a6801ed7b22e20a57'


def review_recorded_splits(*, timing_reviews=(), **kwargs):
    if not timing_reviews:
        return legacy(**kwargs)
    actions={r['payload']['action_id']:r['payload'] for r in kwargs['state']['events'] if r['payload']['kind']=='SPLIT_CONFIRMED'}
    proofs={}
    for proof in timing_reviews:
        require(set(proof)=={'schema','action_id','recorded_action_sha256','distribution_at','quote_unit_effective_at','broker_tradable_at','source_references'},'TIMING_FIELDS')
        key=proof['action_id'];require(proof['schema']=='SPLIT_THREE_CLOCK_CONTENT_V1' and key in actions and key not in proofs,'TIMING_ACTION')
        action=actions[key]
        require(proof['recorded_action_sha256']==sha256(canonical(action)).hexdigest(),'TIMING_ACTION_BINDING')
        distribution,quote,broker=map(moment,(proof['distribution_at'],proof['quote_unit_effective_at'],proof['broker_tradable_at']))
        now=moment(kwargs['now'])
        require(distribution<=quote<=now and distribution<=broker<=moment(action['broker_confirmed_at'])<=now,'TIMING_CLOCK_ORDER')
        require(distribution==moment(action['effective_at']),'TIMING_RECORDED_EFFECTIVE_NOT_DISTRIBUTION')
        refs=proof['source_references'];pins=kwargs['action_package']['source_hashes']
        require(type(refs)is list and refs and len(refs)==len(set(refs)) and all(r in pins for r in refs),'TIMING_EVIDENCE_REQUIRED')
        proofs[key]=proof
    path=Path(__file__).resolve().parents[2]/'data/strategy_recorded_split_review_v1.py'
    raw=path.read_bytes();require(sha256(raw).hexdigest()==SOURCE_HASH,'LEGACY_REVIEW_SOURCE_CHANGED')
    source=raw.decode('utf8').replace('\r\n','\n')
    needle="moment(action['effective_at']).astimezone(ZoneInfo('America/New_York')).date() == day"
    require(source.count(needle)==1,'TIMING_MATCH_ANCHOR')
    source=source.replace(needle,"_quote_clock(action).astimezone(ZoneInfo('America/New_York')).date() == day")
    def quote_clock(action):
        return moment(proofs[action['action_id']]['quote_unit_effective_at']) if action['action_id'] in proofs else moment(action['effective_at'])
    namespace={'__name__':'_private_split_timing_review','_quote_clock':quote_clock}
    exec(compile(source,str(path)+':three_clock_candidate','exec'),namespace)
    result=namespace['review_recorded_splits'](**kwargs)
    result['status']='RECORDED_SPLIT_TIMING_CONTENT_ONLY_NOT_UNIT_ADMISSION'
    result['execution_blocked']=True
    result['downstream_blockers']=['QUOTE_OBSERVED_AT_MUST_REACH_QUOTE_UNIT_EFFECTIVE_AT',
                                  'TRAINING_AND_LIMIT_PRICE_COORDINATES_NOT_INTEGRATED',
                                  'SOURCE_AND_BROKER_TIMING_NOT_AUTHENTICATED']
    result['timing_reviews_sha256']=sha256(canonical(list(timing_reviews))).hexdigest()
    result['timing_scope']='CONTENT_ONLY_EXPLICIT_DISTRIBUTION_LEDGER_SEMANTICS; NOT_SOURCE_OR_BROKER_AUTHORIZATION'
    return result
