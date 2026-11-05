"""Fresh-route binding to the configured current target's pinned news calendar.

No public endpoint, copied calendar or production compose modification. The
server lifecycle builder must bind this candidate and approve its source hash.
"""
from inspect import getclosurevars
import json
from types import SimpleNamespace
from core.strategy_account_ledger import require
from data.news_event_calendar_v1 import window
from data.news_event_sources_v1 import moment


def authorized_window(result,valid_until):
    deadline=min(moment(result['valid_until']),moment(valid_until))
    require(moment(result['not_before'])<deadline,'NATIVE_EVENT_AUTH_WINDOW_EMPTY')
    return dict(result,valid_until=deadline.isoformat())


def configured_calendar_window(*,service,discovered_at):
    with service.monthly.snapshot_operation():
        configuration=service.validate_code();target=service.monthly.current()
        require(target is not None,'NATIVE_EVENT_TARGET_REQUIRED')
        target_id=target['target_id']
        require(target_id in configuration['authorizations'],'NATIVE_CONFIG_NEW_TARGET_AUTHORIZATION_REQUIRED')
        reference=configuration['authorizations'][target_id]
        grant=json.loads(service._read(reference['path']))
        proposal=service.monthly_view.require_proposal(target_id=target_id,expected_proposal_id=grant['proposal_id'])
        require(grant['target_id']==target_id,'NATIVE_EVENT_AUTH_TARGET')
        observed=moment(discovered_at);now=moment(service.clock().isoformat())
        require(moment(grant['reviewed_at'])<=observed<=now<moment(grant['valid_until']),'NATIVE_EVENT_AUTH_TIME')
        name=grant['calendar'];calendar_reference=dict(path=reference['files'][name],sha256=grant['source_sha256'][name])
        def unchanged():
            require(service.validate_code()==configuration and service.monthly.current()==target,'NATIVE_EVENT_GENERATION_CHANGED')
            require(service.monthly_view.require_proposal(target_id=target_id,expected_proposal_id=proposal['proposal_id'])==proposal,'NATIVE_EVENT_PROPOSAL_CHANGED')
        facade=SimpleNamespace(root=service.root,source={'calendar':calendar_reference},validate=unchanged)
        result=authorized_window(window(reader=facade,discovered_at=discovered_at),grant['valid_until'])
        unchanged()
        return dict(result,target_id=target_id,proposal_id=proposal['proposal_id'],source_authorization_sha256=reference['sha256'])


def attach_configured_event_calendar(*,prepared,service):
    """Owner-only, before starting the fresh router's lifecycle."""
    require(prepared['observed_daily'].service is service and prepared['monthly'] is service.monthly_view,'NATIVE_EVENT_SERVICE_IDENTITY')
    routes=[route for route in prepared['router'].routes if route.path=='/api/news/events/status']
    require(len(routes)==1,'NATIVE_EVENT_PIPELINE_ROUTE_REQUIRED')
    pipeline=getclosurevars(routes[0].endpoint).nonlocals['pipeline']
    require(pipeline.service is prepared['news_service'],'NATIVE_EVENT_NEWS_IDENTITY')
    def current(stamp):return configured_calendar_window(service=service,discovered_at=stamp)
    pipeline.calendar_window=current
    return dict(prepared,event_pipeline=pipeline,calendar_enabled=True)
