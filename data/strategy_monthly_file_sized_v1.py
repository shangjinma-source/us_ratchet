"""Size-aware monthly file reader retaining the original package validator."""
from hashlib import sha256
import re
from data.current_quantity_v2_monthly_composition import MonthlyFileConfiguration as Original
from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources
from data.current_quantity_v2_difference_plan import require
from data.strategy_sized_read_v1 import read_sized_source


class MonthlyFileConfiguration(Original):
    def _read(self, path, expected, limit=32*1024*1024):
        CurrentQuantityV2CurrentCashSources._path(path)
        require(type(expected) is str and re.fullmatch('[a-f0-9]{64}', expected), 'INVALID_MONTHLY_CONFIGURATION')
        root = self.root.resolve(); target = root/path
        require(not target.is_symlink() and target.resolve().is_relative_to(root), 'MONTHLY_SOURCE_UNAVAILABLE')
        require(target.is_file() and target.stat().st_size <= limit, 'MONTHLY_SOURCE_UNAVAILABLE')
        with target.open('rb') as source:
            raw = read_sized_source(source, limit)
        require(len(raw) <= limit and sha256(raw).hexdigest() == expected, 'REGISTRY_SOURCE_CHANGED')
        return raw
