"""Explicit, pinned policy-application review after strict source admission.

The source producer remains unbound. Merely passing a release never enables
application: a separate server authorization must fix the complete scope.
"""
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
from core.strategy_account_ledger import canonical,require
from data.strategy_daily_domain_packet_reader_v1 import DomainSessionDailyPacketReaderV1
from data.strategy_daily_domain_policy_review_v1 import review_domain_policy
from data.strategy_daily_dynamic_factory_v1 import FACTORY_SOURCES
from data.strategy_daily_signal_verifier import CODE_PATHS,verify_daily_signal_bundle
from data.strategy_daily_rebound_archive import archive_rebound_evidence
from data.strategy_daily_rolling_parent_v3 import pinned,bounded_read
from data.strategy_daily_session_capture import reject_links,stamp
from data.strategy_continuous32_target_decision import PROFILE_ID,VERSION,REQUIRED_PINS

REVIEW_SOURCES=FACTORY_SOURCES|CODE_PATHS|set(REQUIRED_PINS)|{
    'data/strategy_daily_domain_packet_reader_v1.py',
    'data/strategy_daily_domain_policy_reader_v1.py',
    'data/strategy_daily_domain_policy_review_v1.py',
    'data/strategy_daily_profile_binding.py',
    'data/strategy_daily_signal_verifier.py',
    'data/strategy_daily_rebound_archive.py',
}


class ExplicitDomainPolicyReviewReaderV1(DomainSessionDailyPacketReaderV1):
    def __init__(self,*,review_configuration_path=None,review_configuration_sha256=None,
                 clock=None,**kwargs):
        super().__init__(**kwargs)
        self.review_reference=(dict(path=review_configuration_path,sha256=review_configuration_sha256)
            if review_configuration_path is not None and review_configuration_sha256 is not None else None)
        self.clock=clock or (lambda:datetime.now(timezone.utc))

    def _authorization(self,state,current,calendar_raw):
        raw=pinned(self.root,self.review_reference)
        config=json.loads(raw)
        require(config['schema']=='SERVER_DOMAIN_POLICY_APPLICATION_REVIEW_V1'
                and config.get('authorized')is True
                and config['scope']=='COMPLETE_CURRENT_SESSION_DOMAIN','DOMAIN_POLICY_AUTHORIZATION_REQUIRED')
        require(config['account_id']==state['account_id']
                and config['selector_profile']==PROFILE_ID and config['selection_method']==VERSION
                and type(config['continuous_iterations'])is int and config['continuous_iterations']==32,
                'DOMAIN_POLICY_AUTHORIZATION_SCOPE')
        require(type(config['authorization_id'])is str and bool(config['authorization_id'].strip())
                and type(config['authorization_source'])is str and bool(config['authorization_source'].strip())
                and config['rule_selection_role'] in ('IMPLEMENTER_RECOMMENDATION_REVIEWED','USER_EXPLICIT_RULE_SELECTION'),
                'DOMAIN_POLICY_AUTHORIZATION_ATTRIBUTION')
        require(stamp(config['authorized_at'])<=stamp(config['valid_from'])<=current<stamp(config['valid_until']),
                'DOMAIN_POLICY_AUTHORIZATION_TIME')
        require(config['source_configuration']==self.reference,'DOMAIN_POLICY_SOURCE_CONFIGURATION')
        source=json.loads(pinned(self.root,self.reference))
        require(config['calendar']==source['calendar'] and
                pinned(self.root,config['calendar'])==calendar_raw,'DOMAIN_POLICY_CALENDAR_BINDING')
        require(REVIEW_SOURCES<={r['path'] for r in config['code_pins']},'DOMAIN_POLICY_CODE_SCOPE')
        for reference in config['code_pins']:
            body=pinned(self.root,reference,maximum=32*1024*1024)
            if reference['path'] in REVIEW_SOURCES:
                require(body==(Path(__file__).resolve().parents[1]/reference['path']).read_bytes(),
                        'DOMAIN_POLICY_EXECUTING_CODE')
        release=pinned(self.root,config['release'])
        archive=Path(config['archive_root'])
        require(not archive.is_absolute() and '..' not in archive.parts and bool(archive.parts),
                'DOMAIN_POLICY_ARCHIVE_PATH')
        destination=self.root/archive;reject_links(destination)
        require(destination.resolve().is_relative_to(self.root) and destination.resolve()!=self.root,
                'DOMAIN_POLICY_ARCHIVE_PATH')
        return raw,config,release,destination

    def _admit(self,*,state,target,current,domain,packets,result,calendar_raw):
        if self.review_reference is None:
            return dict(status='WAIT_POLICY_RELEASE',signal=None,reason='WAIT_POLICY_REVIEW_AUTHORIZATION')
        started=stamp(self.clock());require(current<=started,'DOMAIN_POLICY_CLOCK_REVERSED')
        config_raw,config,release,archive=self._authorization(state,started,calendar_raw)
        source=json.loads(pinned(self.root,self.reference))
        session=result['receipt']['execution_session']['date']
        terminal_path=self.root/source['runs_root']/session/'terminal.json'
        terminal_raw=bounded_read(terminal_path);terminal_hash=sha256(terminal_raw).hexdigest()
        terminal=json.loads(terminal_raw)
        for sid,packet in packets.items():
            reference=terminal['packets'][sid]['receipt_reference']
            expected_path=terminal_path.parent/sha256(sid.encode()).hexdigest()/'receipt.json'
            require(reference['sha256']==packet['trusted_receipt_sha256']
                    and reference['path']==expected_path.relative_to(self.root).as_posix(),
                    'DOMAIN_POLICY_ADMITTED_PACKET_RACE')
        event=dict(schema='DOMAIN_POLICY_APPLICATION_EVENT_V1',
            authorization_sha256=self.review_reference['sha256'],
            authorization_id=config['authorization_id'],source_configuration_sha256=self.reference['sha256'],
            source_terminal_sha256=terminal_hash,account_id=state['account_id'],account_revision=state['revision'],
            target_id=target['target_id'],session=session,
            original_receipt_sha256={sid:packet['trusted_receipt_sha256'] for sid,packet in sorted(packets.items())},
            reviewed_at=started.isoformat(),release_sha256=config['release']['sha256'])
        event_raw=canonical(event);event_id=sha256(event_raw).hexdigest()
        reviewed=review_domain_policy(state=state,target=target,now=started.isoformat(),event_id=event_id,
            domain=domain,packets=packets,release_bytes=release,trusted_release_sha256=config['release']['sha256'],
            calendar_bytes=calendar_raw)
        if reviewed.get('receipt')is None:
            return dict(status='WAIT_SIGNAL',signal=None,reason=reviewed['status'])
        files=reviewed['files'];receipt=reviewed['receipt']
        control_path='policy-authorizations/'+self.review_reference['sha256']+'.json'
        event_path='policy-application-events/'+event_id+'.json'
        for name,body in ((control_path,config_raw),(event_path,event_raw)):
            require(name not in files or files[name]==body,'DOMAIN_POLICY_CONTROL_CONFLICT')
            files[name]=body
        receipt.update(policy_application_authorization=dict(path=control_path,sha256=self.review_reference['sha256']),
            policy_application_event=dict(path=event_path,sha256=event_id),
            source_sha256={name:sha256(body).hexdigest() for name,body in files.items()})
        raw=canonical(receipt)
        verified=verify_daily_signal_bundle(state=state,target=target,now=stamp(self.clock()).isoformat(),
            release_bytes=release,trusted_release_sha256=config['release']['sha256'],
            receipt_bytes=raw,trusted_receipt_sha256=sha256(raw).hexdigest(),files=files,calendar_bytes=calendar_raw)
        require(verified['status']=='DAILY_SIGNAL_READY','DOMAIN_POLICY_FINAL_VERIFICATION')
        archived=archive_rebound_evidence(root=archive,receipt_bytes=raw,files=files)
        # Archive failures and subsequent drift preserve the evidence but never
        # expose a signal. The strict reader is reused, not duplicated.
        finished=stamp(self.clock());require(started<=finished,'DOMAIN_POLICY_CLOCK_REVERSED')
        after,after_config,after_release,after_archive=self._authorization(state,finished,calendar_raw)
        require(after==config_raw and after_release==release and after_archive==archive
                and sha256(bounded_read(terminal_path)).hexdigest()==terminal_hash,'DOMAIN_POLICY_POST_ARCHIVE_DRIFT')
        strict=DomainSessionDailyPacketReaderV1(root=self.root,configuration_path=self.reference['path'],
            configuration_sha256=self.reference['sha256'],archive_root=None)
        checked=strict(state,target,finished)
        require(checked['status']=='WAIT_POLICY_RELEASE' and
                checked.get('reviewed_securities')==sorted(domain['securities']),'DOMAIN_POLICY_SOURCE_POSTCHECK')
        require(finished<stamp(receipt['valid_until']),'DOMAIN_POLICY_SESSION_ENDED')
        verified['signal']['evidence_archive']=archived
        return dict(verified,reason=verified['status'],policy_approved=False,evidence_archive=archived)
