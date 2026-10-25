"""Continuous32 daily admission for the independently pinned rolling pipeline."""
from copy import deepcopy

from data.strategy_daily_rolling_packet_reader_v3 import RollingSessionDailyPacketReaderV3
from data.strategy_profiled_daily_packet_admission import ProfiledCurrentSessionDailyReader
from data.strategy_daily_rolling_admission_v3 import RollingDailyAdmissionV3


class ProfiledRollingSessionDailyReaderV3(ProfiledCurrentSessionDailyReader):
    def __init__(self, **server_options):
        # Inherit the exact profile/release check before reading any signal.
        self.packet_reader = RollingSessionDailyPacketReaderV3(**server_options)


def create_profiled_rolling_packet_admission_v3(
        *, monthly, clock, validate_code, root, server_configuration):
    configuration = deepcopy(server_configuration)
    reader = ProfiledRollingSessionDailyReaderV3(
        root=root, **configuration["evidence"])
    return RollingDailyAdmissionV3(
        monthly=monthly, reader=reader, clock=clock, validate_code=validate_code,
        policy_execution_enabled=configuration.get("policy_execution_enabled", False),
        policy_id=configuration.get("policy_id"),
    )
