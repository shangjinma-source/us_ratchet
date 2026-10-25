"""Archive then publish a current monthly selection, with recoverable admission."""
from datetime import datetime, timezone

from data.strategy_paper_application_descriptor_v2 import require,stamp,NY
from backtest.current_strategy_prospective_paper_book_v2 import _context
from backtest.current_strategy_prospective_paper_admission_reader_v2 import registered_evidence,registered_selection

SOURCE='backtest/current_strategy_paper_monthly_publish_v2.py'


def publish_monthly_target(*,coordinator,admission_store,source_loader,clock=None,fault=None):
    clock=clock or (lambda:datetime.now(timezone.utc));fault=fault or (lambda phase:None)
    now=stamp(clock());app=_context(coordinator.authority,now)
    require(SOURCE in app['code_sha256'],'PAPER_MONTHLY_PUBLISH_CODE_REQUIRED')
    require(coordinator.authority==admission_store.authority,'PAPER_MONTHLY_PUBLISH_AUTHORITY')
    month=now.astimezone(NY).strftime('%Y-%m')
    book=coordinator.read();current=coordinator.current_target_id()
    if current:
        previous=registered_selection(admission_store,current)['selection_result']
        previous_month=previous['payload']['target_month']
        require(previous_month<=month,'PAPER_MONTHLY_PUBLISH_CLOCK_REVERSED')
        if previous_month==month:return dict(status='MONTHLY_TARGET_ALREADY_PUBLISHED',target_id=current)
    if any(order['closed'] is None for order in book['orders'].values()):
        return dict(status='WAIT_PENDING_SETTLEMENT_BEFORE_SELECTION')
    operation='monthly-selection:'+month
    registered=registered_evidence(admission_store,operation_id=operation)
    if registered is not None:
        require(registered['kind']=='SELECTION','PAPER_MONTHLY_OPERATION_KIND')
        result=registered['result']
        require(result['payload']['input_binding']['account_revision']==book['revision'],
                'PAPER_MONTHLY_ARCHIVED_ACCOUNT_CHANGED')
    else:
        admitted=admission_store.load()
        supplied=source_loader(book,now.isoformat())
        captured_at=stamp(clock())
        require(captured_at>=now and captured_at.astimezone(NY).strftime('%Y-%m')==month,
                'PAPER_MONTHLY_CAPTURE_CLOCK')
        require(not {'book','authority','admitted_decisions','admitted_settlements','clock','now'} & set(supplied),
                'PAPER_MONTHLY_SOURCE_CONTEXT_OVERRIDE')
        arguments=dict(supplied,book=book,authority=coordinator.authority,admitted_decisions=admitted['decisions'],
                       admitted_settlements=admitted['settlements'],now=captured_at.isoformat())
        result=admission_store.produce_and_archive_selection(operation,arguments)
        fault('after_archive_before_publish')
    require(result['payload']['target_month']==month,'PAPER_MONTHLY_SELECTION_MONTH')
    # Coordinator rechecks the live session, mark age and account/target CAS.
    published=coordinator.publish_target(result,expected_book_revision=book['revision'],previous_target_id=current)
    return dict(status='MONTHLY_TARGET_PUBLISHED',target_id=published['decision_id'])
