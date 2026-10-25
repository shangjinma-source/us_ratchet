"""Reuse saved-training compilation and verified quote/action capture for paper selection."""
from datetime import datetime,timezone
from hashlib import sha256
from copy import deepcopy
from pathlib import Path
from time import monotonic

from core.strategy_account_ledger import canonical
from data.strategy_paper_application_descriptor_v2 import require,stamp,SCOPE
from backtest.current_strategy_prospective_paper_book_v2 import _context,replay
from data.strategy_prospective_paper_selection_v2 import CODE_PATHS,build_prospective_target_inputs
from data.strategy_prospective_paper_source_capture_v2 import capture_prospective_sources,_save
from data.strategy_prospective_paper_unit_review_v2 import review_prospective_execution_sources,_exposure_context

SOURCE='data/strategy_prospective_paper_selection_sources_v2.py'


def capture_selection_sources(*,book,authority,admitted_decisions,admitted_settlements,
        training_provider,identity_resolver,securities,output_directory,clock=None,**transports):
    clock=clock or (lambda:datetime.now(timezone.utc))
    started=monotonic();timings={}
    app=_context(authority,clock())
    require(SOURCE in app['code_sha256'],'PAPER_SELECTION_SOURCE_CODE_REQUIRED')
    checked=replay(book,authority=authority,admitted_decisions=admitted_decisions,admitted_settlements=admitted_settlements)
    checkpoint=monotonic();timings['context_seconds']=checkpoint-started
    package,historical=training_provider.training()
    timings['training_seconds']=monotonic()-checkpoint
    package=deepcopy(package);candidates=set(historical['prices'])
    times,_,exposure=_exposure_context(checked)
    needed=candidates | exposure
    require(needed<=set(securities),'PAPER_SELECTION_SOURCE_IDENTITY_DOMAIN')
    window=min([training_provider.closed]+times,key=stamp)
    checkpoint=monotonic()
    captured=capture_prospective_sources(book=checked,authority=authority,admitted_decisions=admitted_decisions,
        admitted_settlements=admitted_settlements,identity_resolver=identity_resolver,
        securities={sid:securities[sid] for sid in needed},target_quantities={sid:0 for sid in candidates},
        window_start=window,output_directory=output_directory,clock=clock,**transports)
    timings['capture_seconds']=monotonic()-checkpoint;checkpoint=monotonic()
    reviewed=review_prospective_execution_sources(book=checked,authority=authority,admitted_decisions=admitted_decisions,
        admitted_settlements=admitted_settlements,securities={sid:securities[sid] for sid in needed},
        market_capture=captured['market_capture'],action_package=captured['action_capture'],
        training_manifest_sha256=training_provider.manifest_hash,
        historical_search_arguments_sha256=sha256(canonical(historical)).hexdigest(),
        historical_price_basis=historical['price_basis'],training_closed_at=training_provider.closed,clock=clock)
    timings['review_seconds']=monotonic()-checkpoint;checkpoint=monotonic()
    def add(path,raw):
        require(path not in package['files'] or package['files'][path]==raw,'PAPER_SELECTION_SOURCE_COLLISION')
        package['files'][path]=raw;package['source_hashes'][path]=sha256(raw).hexdigest()
    for path,raw in reviewed['market_capture']['files'].items():add(path,raw)
    for path in CODE_PATHS:add(path,authority['descriptor_arguments']['code_bytes'][path])
    # Exposure review also covers closed positions' rights. Selection marks only
    # need candidate, currently held and pending securities; retain raw evidence.
    selection_domain=candidates | {sid for sid,q in checked['shares'].items() if q} | {
        order['security_id'] for order in checked['orders'].values() if order['closed'] is None}
    marks={sid:reviewed['market_capture']['marks'][sid] for sid in selection_domain}
    units=deepcopy(reviewed['unit_review'])
    units['securities']={sid:units['securities'][sid] for sid in selection_domain}
    units['marks_sha256']=sha256(canonical(marks)).hexdigest()
    documents={}
    for name,value in [('marks',marks),('units',units)]:
        raw=canonical(value);path='paper-selection/'+sha256(raw).hexdigest()+'.json'
        add(path,raw);documents[name]=path
    now=stamp(clock()).isoformat()
    review=canonical(dict(schema='PROSPECTIVE_PAPER_SOURCE_ADMISSION_V1',scope=SCOPE,
        descriptor_sha256=checked['descriptor_sha256'],account_id=checked['account_id'],account_revision=checked['revision'],
        source_sha256=package['source_hashes'],available_at=now,source_authenticated=False,coverage_complete=False))
    result=dict(source_package=package,manifest_path=training_provider.manifest_path,marks_path=documents['marks'],
        unit_review_path=documents['units'],source_review_bytes=review,trusted_source_review_sha256=sha256(review).hexdigest(),
        maximum_mark_age_seconds=120)
    timings['assembly_seconds']=monotonic()-checkpoint;checkpoint=monotonic()
    build_prospective_target_inputs(book=checked,authority=authority,admitted_decisions=admitted_decisions,
        admitted_settlements=admitted_settlements,now=now,**result)
    timings['input_validation_seconds']=monotonic()-checkpoint
    # Diagnostics are deliberately outside the admitted source package. This
    # receipt measures preparation only, not optimizer or order execution time.
    _save(Path(output_directory)/'selection-timing.json',dict(
        schema='PAPER_SELECTION_PREPARATION_TIMING_V1',candidate_count=len(candidates),
        capture_count=len(needed),stage_seconds=timings,total_seconds=monotonic()-started,
        optimizer_measured=False,orders_created=False))
    return result
