"""Registered paper replay to the shared daily evidence verifier."""
from copy import deepcopy
from hashlib import sha256
import json
from core.strategy_account_ledger import canonical
from data.strategy_paper_application_descriptor_v2 import require,stamp,SCOPE
from backtest.current_strategy_prospective_paper_book_v2 import replay,project,_context
from data.strategy_prospective_paper_selection_v2 import verify_prospective_target,CODE_PATHS as SELECTION_PINS
from data.strategy_daily_signal_common_v1 import _verify_daily_signal_core,CODE_PATHS as DAILY_RULE_PINS

CODE_PATHS=set(SELECTION_PINS)|set(DAILY_RULE_PINS)|{'data/strategy_prospective_paper_source_daily_v2.py',
    'data/strategy_daily_signal_common_v1.py'}


def verify_prospective_daily(*,book,authority,admitted_decisions,selection_result,selection_arguments,
        now,release_path,receipt_bytes,trusted_receipt_sha256,files,admitted_settlements=None):
    app=_context(authority,now)
    require(CODE_PATHS<=set(app['code_sha256']),'PROSPECTIVE_DAILY_CODE_SCOPE')
    current=replay(book,authority=authority,admitted_decisions=admitted_decisions,admitted_settlements=admitted_settlements)
    selected=verify_prospective_target(selection_result,**selection_arguments)
    previous=replay(selection_arguments['book'],authority=selection_arguments['authority'],
        admitted_decisions=selection_arguments['admitted_decisions'],admitted_settlements=selection_arguments.get('admitted_settlements'))
    require(previous['descriptor_sha256']==current['descriptor_sha256'] and
        previous['registration_sha256']==current['registration_sha256'] and
        previous['revision']==selected['account_revision'] and
        len(previous['operations'])<=len(current['operations']) and
        previous['operations']==current['operations'][:len(previous['operations'])],
        'PROSPECTIVE_SELECTION_NOT_ANCESTOR')
    require(stamp(current['last_available_at'])<=stamp(now),'PROSPECTIVE_DAILY_STATE_FUTURE')
    release=authority['descriptor_arguments']['source_bytes'][release_path]
    release_hash=sha256(release).hexdigest()
    require(app['source_sha256'][release_path]==release_hash,'PROSPECTIVE_DAILY_RELEASE_BINDING')
    if receipt_bytes is not None:
        require(type(receipt_bytes) is bytes and sha256(receipt_bytes).hexdigest()==trusted_receipt_sha256,
            'PROSPECTIVE_DAILY_RECEIPT_HASH')
        receipt=json.loads(receipt_bytes)
        require(stamp(receipt['available_at'])>=max(stamp(current['last_available_at']),
            stamp(selection_result['payload']['computation_finished_at'])),'PROSPECTIVE_DAILY_RECEIPT_BEFORE_STATE')
    state=project(book,authority=authority,admitted_decisions=admitted_decisions,admitted_settlements=admitted_settlements)
    state['orders']={o['order_id']:dict(o,status='OPEN') for o in state['pending_orders']}
    target=dict(target_id=selected['target_id'],payload=dict(account_id=current['account_id'],
        target_month=selected['target_month'],target_quantities=deepcopy(selected['target_quantities'])))
    result=_verify_daily_signal_core(application_kind='PAPER',state=state,target=target,now=now,
        release_bytes=release,trusted_release_sha256=release_hash,receipt_bytes=receipt_bytes,
        trusted_receipt_sha256=trusted_receipt_sha256,files=files,
        calendar_bytes=authority['descriptor_arguments']['calendar_bytes'])
    return dict(result,scope=SCOPE,descriptor_sha256=current['descriptor_sha256'],
        registration_sha256=current['registration_sha256'],account_revision=current['revision'],
        target_id=selected['target_id'],orders_created=False)
