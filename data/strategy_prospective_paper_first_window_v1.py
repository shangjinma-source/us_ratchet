"""Pre-registration paper source review; no account, target, or policy authority."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from core.strategy_account_ledger import canonical, require
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_daily_session_capture import stamp, reject_links
from data.strategy_daily_rolling_parent_v3 import pinned
from data.strategy_verified_context_first_window_v1 import review_first_window, SOURCES

CODE_PATHS=SOURCES|{'data/strategy_prospective_paper_first_window_v1.py'}


def review_paper_first_window(*,root,configuration_bytes,configuration_sha256,capture_files,clock=None):
    """A reviewed source packet can later be pinned; success is not registration."""
    clock=clock or (lambda:datetime.now(timezone.utc));began=stamp(clock())
    root=Path(root).absolute();reject_links(root)
    original=deepcopy(capture_files)
    require(sha256(configuration_bytes).hexdigest()==configuration_sha256,'PAPER_FIRST_CONFIG_HASH')
    config=json.loads(configuration_bytes)
    require(config['schema']=='PAPER_FIRST_WINDOW_SOURCE_PREPARATION_V1','PAPER_FIRST_SCHEMA')
    require(config.get('release_sha256') is None,'PAPER_FIRST_NO_RELEASE')
    require(CODE_PATHS<={r['path'] for r in config['source_pins']},'PAPER_FIRST_CODE_SCOPE')
    snapshots={}
    def read(ref):
        raw=pinned(root,ref,maximum=32*1024*1024);snapshots[(ref['path'],ref['sha256'])]=raw
        return raw
    for ref in config['source_pins']:
        raw=read(ref)
        if ref['path'] in CODE_PATHS:
            require(raw==(Path(__file__).resolve().parents[1]/ref['path']).read_bytes(),'PAPER_FIRST_CODE_CHANGED')
    training=json.loads(read(config['training']))
    identity=json.loads(read(config['identity']))
    sid=config['security_id']
    members=[r for r in training['candidates'] if r['security_id']==sid]
    require(len(members)==1,'PAPER_FIRST_TRAINING_DOMAIN')
    member=members[0]
    resolved=PinnedStrategyIdentity(root,config['identity']['path'],config['identity']['sha256'])(member['ticker'])
    require(resolved['security_id']==sid,'PAPER_FIRST_IDENTITY')
    for name,digest in resolved['source_hashes'].items():read(dict(path=name,sha256=digest))
    read(config['calendar'])
    review_raw=read(config['baseline_review']);review=json.loads(review_raw)
    marks_raw=read(config['baseline_marks']);marks=json.loads(marks_raw)
    complete=json.loads(read(config['baseline_complete']))
    review_name=complete['documents']['unit_review'];marks_name=complete['documents']['marks']
    require(complete['status']=='EVIDENCE_ASSEMBLED_NOT_EXECUTED'
        and complete['source_hashes'][review_name]==sha256(review_raw).hexdigest()
        and complete['source_hashes'][marks_name]==sha256(marks_raw).hexdigest(),'PAPER_FIRST_SAVED_CLOSURE')
    require(review['schema']=='STRATEGY_TARGET_UNIT_REVIEW_V1'
        and review['status']=='CONDITIONAL_CURRENT_UNITS_REVIEWED'
        and review['training_manifest_sha256']==config['training']['sha256']
        and review['training_cutoff_date']==training['decision_date']
        and review['marks_sha256']==sha256(marks_raw).hexdigest()
        and review['unresolved']==[] and review['pending_rights']==[]
        and stamp(review['reviewed_at'])<=began,'PAPER_FIRST_BASELINE')
    unit=review['securities'][sid]
    require(unit['security_id']==sid and unit['training_manifest_sha256']==config['training']['sha256']
        and unit['current_mark_sha256']==sha256(canonical(marks[sid])).hexdigest()
        and unit['current_price_basis']==marks[sid]['price_basis']
        and unit['historical_scenarios_usable_in_current_units'] is True
        and unit['held_quantities_in_current_units'] is True,'PAPER_FIRST_UNIT_BINDING')
    source_hashes={name:complete['source_hashes'][name] for name in unit['source_references']}
    for name,digest in source_hashes.items():read(dict(path=config['unit_source_paths'][name],sha256=digest))
    baseline=dict(review_reference=dict(path=review_name,sha256=sha256(review_raw).hexdigest()),
        reviewed_at=review['reviewed_at'],unit=unit,source_hashes=source_hashes)
    core_config=dict(config,schema='VERIFIED_CONTEXT_FIRST_DAILY_WINDOW_V1')
    core_config['unit_source_paths']=dict(config['unit_source_paths'],**{review_name:config['baseline_review']['path']})
    raw=canonical(core_config)
    result=review_first_window(root=root,configuration_bytes=raw,configuration_sha256=sha256(raw).hexdigest(),
        capture_files=capture_files,entry=dict(ticker=member['ticker'],identity=resolved),baseline=baseline,
        training_cutoff_date=training['decision_date'],origin_reference='paper-source-training:'+config['training']['sha256'],clock=clock)
    for (name,digest),body in snapshots.items():
        require(pinned(root,dict(path=name,sha256=digest),maximum=32*1024*1024)==body,'PAPER_FIRST_SOURCE_CHANGED')
    require(original==capture_files,'PAPER_FIRST_CAPTURE_CHANGED')
    finished=stamp(clock());require(finished>=began,'PAPER_FIRST_CLOCK')
    if result['receipt'] is not None:
        require(finished<stamp(result['receipt']['valid_until']),'PAPER_FIRST_EXPIRED')
        # Retain all explicit original trust inputs in the saved evidence closure.
        for (name,digest),body in snapshots.items():
            require(name not in result['files'] or result['files'][name]==body,'PAPER_FIRST_COLLISION')
            result['files'][name]=body
        name='paper-first-window/configuration/'+configuration_sha256+'.json'
        result['files'][name]=configuration_bytes
        require(len(result['files'])<=2000 and sum(map(len,result['files'].values()))<=32*1024*1024,'PAPER_FIRST_BUDGET')
        result['receipt']['source_sha256']={n:sha256(b).hexdigest() for n,b in result['files'].items()}
        result['receipt']['available_at']=finished.isoformat()
        result['receipt']['valid_from']=max(finished,stamp(result['receipt']['execution_session']['open'])).isoformat()
    return dict(result,book_created=False,registration_created=False,orders_created=False,
        historical_baseline_account_authority_inherited=False)
