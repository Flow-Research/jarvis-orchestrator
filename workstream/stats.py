"""Test-only and throwaway-local operator accounting read models."""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import OperatorStats


@dataclass
class InMemoryOperatorStats:
    """Small test/local read model, not the default production stats path."""

    _stats: dict[str, OperatorStats] = field(default_factory=dict)

    def set_operator_stats(self, stats: OperatorStats) -> None:
        self._stats[stats.operator_id] = stats

    def get_operator_stats(self, operator_id: str) -> OperatorStats:
        return self._stats.get(operator_id) or OperatorStats(operator_id=operator_id)
