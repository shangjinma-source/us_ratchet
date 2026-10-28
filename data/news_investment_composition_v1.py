"""Server-owned binding for optional advisory review; no financial writes."""
from data.news_investment_service_v1 import NewsInvestmentService
from api.news_investment_review_v1 import create_router


def compose(*, root, monthly_view, observed_daily, validate, background_configuration=None):
    # Optional server-owned index; absent at startup preserves existing behavior.
    from pathlib import Path
    import json
    index_path = Path(root)/'data/cache/news/background_index_v1.json'
    index_bytes = None
    if background_configuration is None and index_path.exists():
        index_bytes = index_path.read_bytes()
        background_configuration = json.loads(index_bytes)
    if background_configuration is not None:
        from copy import deepcopy
        background_configuration = deepcopy(background_configuration)
        from data.news_background_context_v1 import verify_manifest, load_background
        original_validate = validate
        def validate():
            original_validate()
            if index_bytes is not None and index_path.read_bytes() != index_bytes:
                raise ValueError('BACKGROUND_INDEX_CHANGED')
            verify_manifest(root, background_configuration)
        validate()
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
    if background_configuration is not None:
        from data.news_investment_model_v1 import analyze_review
        from data.news_event_model_v1 import analyze_event
        context_binding = {'manifest_sha256': background_configuration['manifest_sha256'], 'role': 'BACKGROUND_NOT_TRIGGER'}
        def context_guard(answer):
            validate()
            if answer.get('background_context_binding') != context_binding:
                raise ValueError('BACKGROUND_CONTEXT_VERSION_CHANGED')
        service.background_guard = context_guard
        def account_model(sources, positions, cache, **kwargs):
            backgrounds = load_background(root, background_configuration, sources, positions, service.clock())
            answer = analyze_review(sources, positions, cache, background_sources=backgrounds, **kwargs)
            answer['background_context_binding'] = deepcopy(context_binding)
            return answer
        def event_model(sources, positions, cache, **kwargs):
            backgrounds = load_background(root, background_configuration, sources, positions, service.clock())
            answer = analyze_event(sources, positions, cache, background_sources=backgrounds, **kwargs)
            answer['background_context_binding'] = deepcopy(context_binding)
            return answer
        service.model = account_model
        pipeline.analyzer = event_model
        old_event_guard = pipeline.valid_event
        def guarded_event(pending):
            try:
                context_guard(pending['answer'])
                return old_event_guard(pending)
            except (ValueError, KeyError, OSError):
                return False
        pipeline.valid_event = guarded_event
    service.event_guard = pipeline.valid_event
    router = create_router(service=service, root=root, validate=validate)
    router.include_router(create_event_router(pipeline=pipeline, validate=validate))
    router.add_event_handler('startup', pipeline.start_worker)
    router.add_event_handler('shutdown', pipeline.stop_worker)
    return router
