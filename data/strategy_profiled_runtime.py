"""Explicit server profile dispatch. Never relabel an existing target."""
from core.strategy_account_ledger import require
from data.strategy_account_runtime import build_runtime as build_original
from data.strategy_continuous32_runtime import build_runtime as build_continuous32
from data.strategy_continuous32_target_decision import PROFILE_ID

def build_runtime(*,root,configuration,clock=None):
    if configuration.get('schema')=='REAL_STRATEGY_RUNTIME_V1':
        require('selector_profile' not in configuration,'ORIGINAL_PROFILE_FIELDS')
        return build_original(root=root,configuration=configuration,clock=clock)
    require(configuration.get('schema')=='REAL_STRATEGY_CONTINUOUS32_RUNTIME_V1' and
            configuration.get('selector_profile')==PROFILE_ID,'UNKNOWN_SELECTOR_PROFILE')
    return build_continuous32(root=root,configuration=configuration,clock=clock)
