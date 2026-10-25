"""Server-configured continuous32 packet admission, disabled unless explicitly enabled.

The subclass preserves the existing composition's archived-reader boundary; its
delegate still verifies and archives every admitted signal. No legacy fallback.
"""
from copy import deepcopy

from data.strategy_daily_packet_reader import CurrentSessionDailyPacketReader
from data.strategy_daily_rebinding_reader import ArchivedRebindingDailyEvidenceReader
from data.strategy_daily_profile_binding import validate_daily_profile_binding
from data.strategy_daily_rolling_admission_v3 import RollingDailyAdmissionV3
from data.strategy_daily_session_capture import pinned


class ProfiledCurrentSessionDailyReader(ArchivedRebindingDailyEvidenceReader):
    def __init__(self, **server_options):
        self.packet_reader = CurrentSessionDailyPacketReader(**server_options)

    def __call__(self, state, target, now):
        reader = self.packet_reader
        if reader.release_path is not None and reader.release_sha is not None:
            release = pinned(reader.root, dict(path=reader.release_path, sha256=reader.release_sha))
            validate_daily_profile_binding(release_bytes=release,
                trusted_release_sha256=reader.release_sha, target=target)
        return reader(state, target, now)


def create_profiled_packet_admission(*, monthly, clock, validate_code, root,
                                    server_configuration):
    config = deepcopy(server_configuration)
    reader = ProfiledCurrentSessionDailyReader(root=root, **config["evidence"])
    return RollingDailyAdmissionV3(monthly=monthly, reader=reader, clock=clock,
        validate_code=validate_code, policy_execution_enabled=config.get("policy_execution_enabled", False),
        policy_id=config.get("policy_id"))
