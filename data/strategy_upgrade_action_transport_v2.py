"""Explicit pinned action transport override for isolated upgrade runtime builds."""
from hashlib import sha256
from pathlib import Path
from core.strategy_account_difference import require
from core.strategy_account_ledger import canonical
from data.strategy_account_runtime_archive import _document
from data.strategy_bounded_source_gate_v1 import _no_links
from data.strategy_profiled_runtime import build_runtime
from data.strategy_account_action_capture import StrategyAccountActionCapture
from data.strategy_account_action_capture_v2 import StrategyAccountActionCaptureV2
from scripts.register_quantity_v2_paper_protocol import safe_path

SOURCES={'data/strategy_upgrade_action_transport_v2.py','data/strategy_account_action_capture_v2.py',
         'scripts/run_continuous32_upgrade.py'}
ROOT=Path(__file__).resolve().parents[1]


class PinnedUpgradeActionTransportV2:
    def __init__(self,*,root,configuration_path,configuration_sha256):
        self.root=Path(root).absolute();self.path=configuration_path;self.digest=configuration_sha256
        self.configuration=self._configuration()
        self.validate()

    def _configuration(self):
        path=safe_path(self.root,self.path);_no_links(path)
        with path.open('rb') as stream:raw=stream.read(1024*1024+1)
        require(len(raw)<=1024*1024 and sha256(raw).hexdigest()==self.digest,'ACTION_TRANSPORT_CONFIG_CHANGED')
        value=_document(raw)
        require(set(value)=={'schema','authorized','max_workers','capture_window_seconds','source_pins'} and
                value['schema']=='PINNED_UPGRADE_ACTION_TRANSPORT_V2' and value['authorized'] is True and
                type(value['max_workers'])is int and value['max_workers']==4 and
                type(value['capture_window_seconds'])is int and value['capture_window_seconds']==120 and
                set(value['source_pins'])==SOURCES,'ACTION_TRANSPORT_CONFIGURATION_INVALID')
        return value

    def validate(self):
        require(self._configuration()==self.configuration,'ACTION_TRANSPORT_CONFIG_CHANGED')
        for name,digest in self.configuration['source_pins'].items():
            for path in (safe_path(self.root,name),ROOT/name):
                _no_links(path)
                with path.open('rb') as stream:raw=stream.read(4*1024*1024+1)
                require(len(raw)<=4*1024*1024 and sha256(raw).hexdigest()==digest,'ACTION_TRANSPORT_SOURCE_CHANGED')

    def build_runtime(self,**kwargs):
        self.validate()
        runtime=build_runtime(**kwargs)
        provider=runtime.execution_provider.__self__
        original=provider.actions
        require(type(original)is StrategyAccountActionCapture,'ACTION_TRANSPORT_ORIGINAL_REQUIRED')
        gate=self.validate
        class AdmittedCapture(StrategyAccountActionCaptureV2):
            def capture(self,request,output_directory):
                gate()
                try:return super().capture(request,output_directory)
                finally:gate()
        provider.actions=AdmittedCapture(fetch=original.fetch,rss_fetch=original.rss_fetch,
                                        clock=original.clock,max_workers=4)
        self.validate()
        return runtime


def materialize_transport_configuration(*,root,relative_path,authorized=False):
    require(type(authorized)is bool,'ACTION_TRANSPORT_AUTHORIZATION_REQUIRED')
    root=Path(root).absolute();path=safe_path(root,relative_path);_no_links(path)
    pins={name:sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCES}
    for name,digest in pins.items():
        require(sha256(safe_path(root,name).read_bytes()).hexdigest()==digest,'ACTION_TRANSPORT_SOURCE_CHANGED')
    value=dict(schema='PINNED_UPGRADE_ACTION_TRANSPORT_V2',authorized=authorized,
               max_workers=4,capture_window_seconds=120,source_pins=pins)
    raw=canonical(value);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(raw)
    return dict(path=relative_path,sha256=sha256(raw).hexdigest())
