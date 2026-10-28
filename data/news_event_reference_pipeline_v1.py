"""Explicit discovery-only port for the unchanged bounded event pipeline."""
from data.news_event_pipeline_v1 import EventNewsPipeline


class _DiscoveryServicePort:
    def __init__(self, service):
        object.__setattr__(self, '_service', service)

    def __getattr__(self, name):
        return getattr(self._service, name)

    def __setattr__(self, name, value):
        setattr(self._service, name, value)

    def bound_context(self, binding):
        # Only pipeline discovery uses this port. Actual jobs/status remain on
        # the original service and its strict persisted reference binding.
        return self._service.preliminary_event_context(binding)


class ReferenceEventNewsPipeline(EventNewsPipeline):
    def __init__(self, service, **kwargs):
        if not callable(getattr(service, 'preliminary_event_context', None)):
            raise ValueError('REFERENCE_EVENT_CONTEXT_REQUIRED')
        super().__init__(_DiscoveryServicePort(service), **kwargs)
