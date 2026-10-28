"""Unrouted reference-bound AI review subclass; no model or trading authority added."""
from contextvars import ContextVar
from copy import deepcopy
from data.news_investment_service_v1 import NewsInvestmentService
from core.reentry_buy_scope_v1 import require, valid_hash

KEY = '_server_reference_binding'


class NewsInvestmentReferenceService(NewsInvestmentService):
    def __init__(self, *, reference_reader, **kwargs):
        require(callable(reference_reader), 'REFERENCE_READER_REQUIRED')
        self.reference_reader = reference_reader
        self._running_binding = ContextVar('reference_review_binding', default=None)
        preview = kwargs['preview']
        model = kwargs.get('model')
        provider = kwargs.get('risk_plan_provider')

        def checked_preview(**binding):
            self.check_reference(binding)
            result = preview(**{k:v for k,v in binding.items() if k != KEY})
            self.check_reference(binding)
            summary = result.get('reference_projection', {})
            require(all(summary.get(k) == binding[KEY][k] for k in
                        ('reference_version','reference_state_sha256','configuration_sha256')),
                    'REFERENCE_PREVIEW_BINDING_CHANGED')
            require(result.get('policy_id') == 'SAVED_FRONTIER_CAP50_EXIT20_REENTRY_V1',
                    'REFERENCE_FILTERED_PREVIEW_REQUIRED')
            return result

        def checked_model(*args, **options):
            binding = self._running_binding.get()
            self.check_reference(binding)
            from data.news_investment_model_v1 import analyze_review
            answer = (model or analyze_review)(*args, **options)
            self.check_reference(binding)
            return answer

        def checked_plan(**arguments):
            binding = self._running_binding.get()
            self.check_reference(binding)
            from data.news_risk_plan_v1 import build_risk_plan
            if provider is None:
                result = build_risk_plan(proposal=arguments['proposal'],
                    original_preview=arguments['original'], account=arguments['account'], now=arguments['now'])
            else:
                result = provider(**arguments)
            self.check_reference(binding)
            if result.get('status') == 'READY':
                targets = arguments['original']['effective_target_quantities']
                for row in result.get('rows', []):
                    quantity = row['planned_target_quantity']
                    require(type(quantity) is int and 0 <= quantity <= targets.get(row['security_id'], 0),
                            'AI_CANNOT_RELEASE_REFERENCE_BUY_LOCK')
                shares = arguments['account']['shares']
                for order in result.get('candidate_orders', []):
                    if order['side'] == 'BUY':
                        require(order['quantity'] <= max(0, targets.get(order['security_id'],0)-shares.get(order['security_id'],0)),
                                'AI_CANNOT_RELEASE_REFERENCE_BUY_LOCK')
            return result

        kwargs.update(preview=checked_preview, model=checked_model, risk_plan_provider=checked_plan)
        super().__init__(**kwargs)

    def reference_snapshot(self):
        result = deepcopy(self.reference_reader())
        require(type(result) is dict and set(result) == {'account_id','reference_version',
                    'reference_state_sha256','configuration_sha256'}, 'REFERENCE_CURRENT_STATE_REQUIRED')
        require(type(result['account_id']) is str and bool(result['account_id']) and
                type(result['reference_version']) is int and result['reference_version'] >= 0 and
                valid_hash(result['reference_state_sha256']) and valid_hash(result['configuration_sha256']),
                'REFERENCE_CURRENT_STATE_INVALID')
        return result

    def check_reference(self, binding):
        require(type(binding) is dict and KEY in binding and
                binding[KEY] == self.reference_snapshot(), 'REFERENCE_REVIEW_CHANGED')

    def bound_context(self, binding):
        self.check_reference(binding)
        result = super().bound_context({k:v for k,v in binding.items() if k != KEY})
        require(result[0]['account_id'] == binding[KEY]['account_id'], 'REFERENCE_ACCOUNT_CHANGED')
        self.check_reference(binding)
        return result

    def start(self, binding, *, event_pending=None):
        require(KEY not in binding, 'CLIENT_REFERENCE_BINDING_FORBIDDEN')
        bound = dict(binding, **{KEY:self.reference_snapshot()})
        return super().start(bound, event_pending=event_pending)

    def preliminary_event_context(self, binding):
        """Public-source discovery context only; never a job or proposal guard.

        A source-only opinion can later be rebound at the first executable
        window. start/start_event independently seals the actual review job.
        """
        require(type(binding) is dict and set(binding) == {
            'expected_revision', 'target_id', 'expected_proposal_id'},
            'EVENT_PRELIMINARY_REQUEST_BINDING')
        return self.bound_context(dict(binding, **{KEY:self.reference_snapshot()}))

    def run(self, job):
        token = self._running_binding.set(deepcopy(job['binding']))
        try:
            return super().run(job)
        finally:
            self._running_binding.reset(token)

    def status(self, job_id):
        # Base COMPLETE path invokes our bound_context; RUNNING exposes no proposal.
        return super().status(job_id)
