"""Reuse reviewed monthly publications as paper training, without activation."""
from hashlib import sha256

from core.strategy_account_ledger import canonical
from data.strategy_account_monthly_release import resolve_monthly_runtime
from data.strategy_account_evidence_provider import StrategyAccountEvidenceProvider
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_paper_application_descriptor_v2 import require


def load_monthly_training(*,root,registry_path,registry_sha256,runtime_pins,output_root,clock):
    # The same resolver replays publication hashes, compiler, identities and dates.
    # It reads market evidence only; do not invoke real-account activation here.
    config=resolve_monthly_runtime(root=root,registry_path=registry_path,
        registry_sha256=registry_sha256,clock=clock)
    provider=StrategyAccountEvidenceProvider(root=root,manifest_path=config['training_manifest'],
        manifest_sha256=config['training_sha256'],training_closed_at=config['training_closed_at'],
        market_capture=None,action_capture=None,limits_builder=None,output_root=output_root,
        runtime_pins=runtime_pins,clock=clock)
    _,historical=provider.training()
    identity=PinnedStrategyIdentity(root,config['identity_manifest'],config['identity_sha256'])
    securities={}
    for sid,metadata in historical['metadata'].items():
        if sid not in historical['prices']:continue
        resolved=identity(metadata['ticker'])
        require(resolved['security_id']==sid,'PAPER_MONTHLY_TRAINING_IDENTITY')
        securities[sid]=dict(metadata)
    context=dict(training_manifest_sha256=config['training_sha256'],
        historical_search_arguments_sha256=sha256(canonical(historical)).hexdigest(),
        historical_price_basis=historical['price_basis'],training_closed_at=config['training_closed_at'])
    return dict(target_month=config['target_month'],provider=provider,identity=identity,
        securities=securities,training_context=context,
        registry_reference=dict(path=registry_path,sha256=registry_sha256),
        training_reference=dict(path=config['training_manifest'],sha256=config['training_sha256']))
