"""Isolated consumer guard; three-clock content is not current-unit admission."""
from types import FunctionType
from core.strategy_account_ledger import require
from docs.candidates.strategy_account_split_unit_review import review_interval as original
from data.strategy_recorded_split_review_v1 import review_recorded_splits as legacy


def review_interval(*, split_reviewer=legacy, **arguments):
    def guarded(**kwargs):
        result=split_reviewer(**kwargs)
        require(result.get('status')=='RECORDED_SPLITS_MATCH_CAPTURE_NOT_AUTHORIZED'
                and not result.get('execution_blocked',False)
                and not result.get('downstream_blockers'),
                'SPLIT_CONTENT_ONLY_NOT_CURRENT_UNIT_ADMISSION')
        return result
    # Private globals avoid mutating an imported consumer or concurrent callers.
    namespace=dict(original.__globals__,review_recorded_splits=guarded)
    isolated=FunctionType(original.__code__,namespace,original.__name__,original.__defaults__,original.__closure__)
    isolated.__kwdefaults__=original.__kwdefaults__
    return isolated(**arguments)
