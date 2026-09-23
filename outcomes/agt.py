"""Bind to the Agent SRE Governance SLI contract.

Everything in this package is an SLI in the sense of *Agent SRE Governance 1.0*
section 4: it extends `SLI`, records `SLIValue`s, aggregates over a
`TimeWindow`, and can be added to an `SLIRegistry`.

When `agent_sre` is installed, those are its real classes and these SLIs are
drop-in. When it is not, the fallbacks below implement the same specification
so the package stays testable on its own. The fallbacks exist to keep the tests
honest, not to fork the contract — if the two ever disagree, the installed
implementation is right.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

try:  # pragma: no cover - exercised by whichever side is installed
    from agent_sre.slo.indicators import SLI, SLIRegistry, SLIValue, TimeWindow

    USING_AGENT_SRE = True
except ImportError:  # pragma: no cover
    USING_AGENT_SRE = False

    class TimeWindow(Enum):
        """Agent SRE Governance 1.0 section 4.2."""

        HOUR_1 = "1h"
        HOUR_6 = "6h"
        DAY_1 = "24h"
        DAY_7 = "7d"
        DAY_30 = "30d"

        @property
        def seconds(self) -> int:
            return {"1h": 3600, "6h": 21600, "24h": 86400,
                    "7d": 604800, "30d": 2592000}[self.value]

    @dataclass(frozen=True)
    class SLIValue:
        """Section 4.3. `is_good` compares against the target in metadata."""

        name: str
        value: float
        timestamp: float = field(default_factory=time.time)
        metadata: dict[str, Any] = field(default_factory=dict)

        @property
        def is_good(self) -> bool:
            target = self.metadata.get("target")
            if target is None:
                return True
            return bool(self.value >= target)

    class SLI(ABC):
        """Section 4.1."""

        def __init__(self, name: str, target: float, window: TimeWindow | str) -> None:
            self.name = name
            self.target = target
            self.window = TimeWindow(window) if isinstance(window, str) else window
            self._measurements: list[SLIValue] = []

        @abstractmethod
        def collect(self) -> SLIValue: ...

        def record(self, value: float, metadata: dict[str, Any] | None = None) -> SLIValue:
            measurement = SLIValue(
                name=self.name,
                value=value,
                timestamp=time.time(),
                metadata={"target": self.target, **(metadata or {})},
            )
            self._measurements.append(measurement)
            return measurement

        def values_in_window(self) -> list[SLIValue]:
            cutoff = time.time() - self.window.seconds
            return [m for m in self._measurements if m.timestamp >= cutoff]

        def current_value(self) -> float | None:
            values = self.values_in_window()
            if not values:
                return None
            return sum(v.value for v in values) / len(values)

        def compliance(self) -> float | None:
            values = self.values_in_window()
            if not values:
                return None
            return sum(1 for v in values if v.is_good) / len(values)

        def to_dict(self) -> dict[str, Any]:
            return {
                "name": self.name,
                "target": self.target,
                "window": self.window.value,
                "current_value": self.current_value(),
                "compliance": self.compliance(),
                "measurement_count": len(self.values_in_window()),
            }

    class SLIRegistry:
        """Section 4.8, reduced to the parts an extension needs."""

        def __init__(self) -> None:
            self._indicators: dict[str, type] = {}

        def register_type(self, sli_class: type) -> None:
            self._indicators[sli_class.__name__] = sli_class

        def get_type(self, name: str):
            return self._indicators.get(name)

        def list_types(self) -> list[str]:
            return list(self._indicators)


__all__ = ["SLI", "SLIRegistry", "SLIValue", "TimeWindow", "USING_AGENT_SRE"]
