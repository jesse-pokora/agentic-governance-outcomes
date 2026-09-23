"""CheckPassRate: the fraction of checks that passed, independent of order.

`PolicyCompliance.record_check` records a *running cumulative rate* as each
measurement:

    rate = self._compliant / self._total
    return self.record(rate, metadata)

`compliance()` then reports the fraction of those running rates that met the
target. With a target of 1.0 a running rate is at target only while every check
so far has passed, so the reported figure is really *the fraction of the window
during which nothing had failed yet* — and one early failure holds it near zero
however well the rest of the window goes.

That makes the number order-dependent. Nine passes then one failure reports
0.900; one failure then nine passes reports 0.000. The underlying pass rate is
0.900 in both cases. `tests/test_order_dependence.py` is that comparison.

This SLI records each check as 1.0 or 0.0, so `compliance()` is the pass rate
itself and any permutation of the same checks gives the same answer.

It is an additional view, not a correction. `PolicyCompliance` honours the base
contract exactly — section 4.1 defines `compliance()` as the fraction of
measurements meeting the target, and it is — the surprise is in what it chooses
to record as a measurement. Run both: a large gap between them says failures
are clustered early in the window, which is worth knowing on its own.
"""

from __future__ import annotations

from typing import Any

from agt import SLI, SLIValue, TimeWindow


class CheckPassRate(SLI):
    """Fraction of policy checks that passed, over the window."""

    def __init__(
        self,
        name: str = "check_pass_rate",
        target: float = 1.0,
        window: TimeWindow | str = TimeWindow.DAY_1,
        **kwargs: Any,
    ) -> None:
        super().__init__(name=name, target=target, window=window, **kwargs)

    def record_check(
        self, compliant: bool, metadata: dict[str, Any] | None = None
    ) -> SLIValue:
        """Record one check as itself, not as the story so far."""
        return self.record(1.0 if compliant else 0.0, metadata)

    def passed(self) -> int:
        return sum(1 for v in self.values_in_window() if v.value >= 1.0)

    def checked(self) -> int:
        return len(self.values_in_window())

    def collect(self) -> SLIValue:
        checked = self.checked()
        return self.record(self.passed() / checked if checked else 1.0)


__all__ = ["CheckPassRate"]
