"""Server-owned binding for optional advisory review; no financial writes."""
from data.news_investment_service_v1 import NewsInvestmentService
from api.news_investment_review_v1 import create_router


def compose(*, root, monthly_view, observed_daily, validate):
    def context():
        with monthly_view.snapshot_operation():
            validate()
            account = monthly_view.accounts.read()
            target = monthly_view.current()
            if account is None or target is None:
                raise ValueError('ACCOUNT_AND_TARGET_REQUIRED')
            metadata = target['payload']['decision']['payload']['input_binding']['search_arguments']['metadata']
            names = {sid: item['ticker'] for sid, item in metadata.items()}
            for event in account['events']:
                identity = event['payload'].get('identity_evidence')
                if identity:
                    sid, ticker = identity['security_id'], identity['ticker']
                    if sid in names and names[sid] != ticker:
                        raise ValueError('SECURITY_TICKER_CONFLICT')
                    names[sid] = ticker
            return account, target, names
    service = NewsInvestmentService(cache=root/'data/cache/news', context=context,
                                   preview=observed_daily.preview, validate=validate)
    from data.news_risk_plan_v1 import build_risk_plan
    from data.news_risk_execution_bridge_v1 import make_hold_risk_plan_adapter

    def project_risk_plan(*, original, proposal, account, target, now):
        if original.get('status') != 'HOLD':
            return build_risk_plan(proposal=proposal, original_preview=original,
                                   account=account, now=now)
        generation = service.news_generation()

        def review_unchanged():
            validate()
            if service.news_generation() != generation:
                raise ValueError('NEWS_UPDATED_DURING_EXECUTION_PREVIEW')
            # The owning service also checks its original pre-analysis news
            # generation, event control and first-window deadline after return.

        adapter = make_hold_risk_plan_adapter(composition=observed_daily.service,
            validate=validate, review_guard=review_unchanged)
        return adapter(original=original, proposal=proposal, account=account,
                       target=target, now=now)

    service.risk_plan_provider = project_risk_plan
    from data.news_event_pipeline_v1 import EventNewsPipeline
    from data.news_event_calendar_v1 import window
    from api.news_event_pipeline_v1 import create_event_router
    pipeline = EventNewsPipeline(service, calendar_window=lambda stamp: window(
        reader=observed_daily.service.reader, discovered_at=stamp))
    service.event_guard = pipeline.valid_event
    router = create_router(service=service, root=root, validate=validate)
    router.include_router(create_event_router(pipeline=pipeline, validate=validate))
    router.add_event_handler('startup', pipeline.start_worker)
    router.add_event_handler('shutdown', pipeline.stop_worker)
    return router
