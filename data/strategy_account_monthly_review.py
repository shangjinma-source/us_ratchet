"""One-shot data review for the real account, independent of cash confirmation.

Zero quantities delimit review coverage only, never a portfolio target. No
selection, limit evaluation or account write is performed by this entry point.
This module requires explicit source-pin admission before future deployment.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import canonical, replay, require
from data.strategy_account_runtime import build_runtime, RUNTIME_PATHS
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_account_market_capture import StrategyAccountMarketCapture
from data.strategy_account_action_capture import StrategyAccountActionCapture
from data.strategy_account_evidence_provider import StrategyAccountEvidenceProvider


class StrategyAccountMonthlyReview:
    def __init__(self, *, root, configuration, output_directory, clock=None,
                 market_capture=None, action_capture=None):
        supplied_root=Path(root).absolute()
        for path in [supplied_root,*supplied_root.parents]:
            require(not path.is_symlink() and not (path.exists() and
                getattr(path.lstat(),'st_file_attributes',0)&0x400),'REVIEW_ROOT_LINK_REFUSED')
        self.root=supplied_root.resolve();self.configuration=deepcopy(configuration)
        self.clock=clock or (lambda:datetime.now(timezone.utc))
        require(type(output_directory) is str and '\\' not in output_directory and ':' not in output_directory
            and not PurePosixPath(output_directory).is_absolute()
            and all(part not in ('','.','..') for part in output_directory.split('/')), 'REVIEW_OUTPUT_INVALID')
        self.output=self.root/output_directory
        self.runtime=build_runtime(root=self.root,configuration=self.configuration,clock=self.clock)
        self.accounts=self.runtime.accounts
        identity=PinnedStrategyIdentity(self.root,self.configuration['identity_manifest'],self.configuration['identity_sha256'])
        def forbidden_limits(**kwargs):raise ValueError('REVIEW_LIMIT_EVALUATION_FORBIDDEN')
        self.provider=StrategyAccountEvidenceProvider(root=self.root,
            manifest_path=self.configuration['training_manifest'],manifest_sha256=self.configuration['training_sha256'],
            training_closed_at=self.configuration['training_closed_at'],
            market_capture=market_capture or StrategyAccountMarketCapture(identity_resolver=identity,clock=self.clock),
            action_capture=action_capture or StrategyAccountActionCapture(clock=self.clock),
            limits_builder=forbidden_limits,output_root=self.output,
            runtime_pins=self.configuration['runtime_pins'],clock=self.clock)
        self.used=False

    def _pins(self):
        self.runtime.selection._pins()
        executing=Path(__file__).resolve().parents[1]
        for path in RUNTIME_PATHS:
            require(sha256((executing/path).read_bytes()).hexdigest()==self.configuration['runtime_pins'][path],
                    'EXECUTING_COMPOSITION_SOURCE_CHANGED')

    def review(self, *, expected_revision):
        with self.runtime.lock:
            require(not self.used,'REVIEW_ALREADY_ATTEMPTED')
            for path in [self.output,*self.output.parents]:
                require(not path.is_symlink() and not (path.exists() and
                    getattr(path.lstat(),'st_file_attributes',0)&0x400),'REVIEW_OUTPUT_LINK_REFUSED')
            require(not self.output.exists(),'REVIEW_CREATE_ONLY_OUTPUT_EXISTS')
            self._pins()
            state=self.accounts.read()
            require(state is not None and state['revision']==expected_revision,'STALE_REVISION')
            require(replay(state['account_id'],[event['payload'] for event in state['events']])==state,'ACCOUNT_REPLAY_MISMATCH')
            now=self.clock()
            require(now.utcoffset() is not None and now.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m')
                    ==self.configuration['target_month'],'CURRENT_MONTH_TRAINING_DEPLOYMENT_REQUIRED')
            package,historical=self.provider.training()
            domain={sid:0 for sid in historical['metadata']}
            self.output.mkdir(parents=True,exist_ok=False)
            self.used=True
            marks=self.provider._assemble(deepcopy(state),package,historical,target_quantities=domain,
                execution_only=True,valuation_only=True)
            children=list(self.output.iterdir())
            require(len(children)==1 and children[0].is_dir(),'REVIEW_CAPTURE_DIRECTORY_INVALID')
            directory=children[0]
            require(not directory.is_symlink() and not (getattr(directory.lstat(),'st_file_attributes',0)&0x400),
                    'REVIEW_OUTPUT_LINK_REFUSED')
            def read(name):
                path=directory/name
                require(not path.is_symlink() and not (getattr(path.lstat(),'st_file_attributes',0)&0x400)
                    and path.is_file() and path.stat().st_size<=32*1024*1024,'REVIEW_RECEIPT_INVALID')
                raw=path.read_bytes();return raw,json.loads(raw)
            _,started=read('started.json');_,complete=read('complete.json')
            raw,review=read('unit_review.json');marks_raw,saved_marks=read('marks.json')
            require(started['account_id']==state['account_id'] and started['revision']==expected_revision
                and review['account_revision']==expected_revision
                and review['training_manifest_sha256']==self.configuration['training_sha256']
                and complete['status']=='EVIDENCE_ASSEMBLED_NOT_EXECUTED','REVIEW_BINDING_MISMATCH')
            require(complete['source_hashes'][complete['documents']['unit_review']]==sha256(raw).hexdigest()
                and complete['source_hashes'][complete['documents']['marks']]==sha256(marks_raw).hexdigest()
                and review['marks_sha256']==sha256(marks_raw).hexdigest() and saved_marks==marks,
                'REVIEW_RECEIPT_HASH_MISMATCH')
            self._pins();current=self.accounts.read()
            require(current is not None and current['revision']==expected_revision,'ACCOUNT_CHANGED_DURING_REVIEW')
            require(self.clock().astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m')
                ==self.configuration['target_month'],'REVIEW_MONTH_CHANGED')
            return dict(status='MONTHLY_ACCOUNT_DATA_REVIEWED',account_id=state['account_id'],
                account_revision=expected_revision,review_path=(directory/'unit_review.json').relative_to(self.root).as_posix(),
                review_sha256=sha256(raw).hexdigest(),complete_path=(directory/'complete.json').relative_to(self.root).as_posix(),
                securities=sorted(marks),cash_confirmation_valid=state['cash_confirmation_valid'],
                zero_quantities_purpose='REVIEW_DOMAIN_ONLY_NOT_TARGET',account_writes=False,search_calls=0,
                limit_calls=0,orders_created=False,reviewed_at=review['reviewed_at'],finished_at=complete['finished_at'],
                limitations=['Known public sources may omit corporate actions.',
                    'This data review is neither a target nor month-long execution authorization.',
                    'Activation and execution must revalidate account revision and fresh quotations.'])
