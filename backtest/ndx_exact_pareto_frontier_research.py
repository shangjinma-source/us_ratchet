"""Exact two-objective minimization frontier, retaining every objective tie."""
from bisect import bisect_left
import math
from numbers import Real


class ExactParetoFrontier:
    """Bucketed frontier with original insertion-order output.

    Objectives are compared with ordinary exact ``<``/``<=`` (no rounding,
    tolerance or scalarization). Payload objects are retained by reference;
    modifying a payload later does not change its snapshotted objective pair.
    ``items`` returns a new list containing the original surviving objects.
    """
    def __init__(self):
        self._coordinates = []
        self._buckets = []
        self._sequence = 0

    def add(self, payload, objectives):
        if (type(objectives) is not tuple or len(objectives) != 2
                or any(not isinstance(value, Real) or isinstance(value, bool)
                       for value in objectives)):
            raise ValueError('Two finite nonboolean real objectives in a tuple required')
        try:
            finite = all(math.isfinite(value) for value in objectives)
        except (OverflowError, TypeError, ValueError):
            finite = False
        if not finite:
            raise ValueError('Objectives must be finite')
        x, fee = objectives
        sequence = self._sequence
        self._sequence += 1
        position = bisect_left(self._coordinates, x)
        # The preceding frontier bucket has the lowest fee among all points
        # with strictly smaller x, hence one comparison proves domination.
        if position > 0 and self._buckets[position-1][0] <= fee:
            return
        if position < len(self._coordinates) and self._coordinates[position] == x:
            existing_fee, entries = self._buckets[position]
            if existing_fee < fee:
                return
            if existing_fee == fee:
                entries.append((sequence, payload))
                return
        # Here any existing same-x bucket is strictly worse. All succeeding
        # buckets with fee >= the new fee are dominated. Fees decrease strictly
        # along the frontier, so removals form one contiguous slice.
        end = position
        while end < len(self._coordinates) and self._buckets[end][0] >= fee:
            end += 1
        self._coordinates[position:end] = [x]
        self._buckets[position:end] = [(fee, [(sequence, payload)])]

    def items(self):
        survivors = [entry for _, entries in self._buckets for entry in entries]
        survivors.sort(key=lambda entry: entry[0])
        return [payload for _, payload in survivors]
