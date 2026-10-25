"""Profile-first, all-security daily admission. No policy is implicitly enabled."""
from copy import deepcopy
from data.strategy_daily_domain_policy_reader_v1 import ExplicitDomainPolicyReviewReaderV1
from data.strategy_profiled_daily_packet_admission import ProfiledCurrentSessionDailyReader
from data.strategy_daily_rolling_admission_v3 import RollingDailyAdmissionV3

class ProfiledReviewedDomainSessionDailyReaderV1(ProfiledCurrentSessionDailyReader):
    def __init__(self,**server_options):
        self.packet_reader=ExplicitDomainPolicyReviewReaderV1(**server_options)

def create_profiled_reviewed_domain_packet_admission_v1(*,monthly,clock,validate_code,root,server_configuration):
    configuration=deepcopy(server_configuration)
    reader=ProfiledReviewedDomainSessionDailyReaderV1(root=root,clock=clock,**configuration['evidence'])
    return RollingDailyAdmissionV3(monthly=monthly,reader=reader,clock=clock,validate_code=validate_code,
        policy_execution_enabled=configuration.get('policy_execution_enabled',False),policy_id=configuration.get('policy_id'))
