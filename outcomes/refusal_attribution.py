"""RefusalAttribution: the fraction of refusals a declared rule explains.

`PolicyCompliance.record_check(compliant=False)` treats every non-compliant
check alike. But a check that failed because a policy said no and a check that
failed because the evaluator raised are different events wearing the same
boolean, and averaging them produces a figure that is part policy and part
defect with no way to separate the two.

So refusals are recorded with the reason the gate gave, and reconciled against
the vocabulary that gate declared. A reason nobody declared is reported as a
defect rather than folded into the rate.

The second output matters as much: rules that never fired. Not a defect — but
either the rule guards something that does not happen, or the case that
triggers it has never been exercised, and those have different remedies.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from agt import SLI, SLIValue, TimeWindow


class AttributionRejected(Exception):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


class RefusalAttribution(SLI):
    """Fraction of refusals carrying a reason the gate declared it could give.

    Target defaults to 1.0. A single unexplained refusal means the compliance
    figure beside this one is mixing policy with defect.
    """

    def __init__(
        self,
        declared_reasons: set[str],
        name: str = "refusal_attribution",
        target: float = 1.0,
        window: TimeWindow | str = TimeWindow.DAY_1,
        **kwargs: Any,
    ) -> None:
        if not declared_reasons:
            raise AttributionRejected(
                "no_declared_reasons", "a vocabulary of nothing explains nothing"
            )
        super().__init__(name=name, target=target, window=window, **kwargs)
        self.declared_reasons = frozenset(declared_reasons)

    def record_refusal(
        self, reason: str, metadata: dict[str, Any] | None = None
    ) -> SLIValue:
        """Record one refusal. 1.0 when the reason was declared, 0.0 when not."""
        if not reason:
            raise AttributionRejected("unstated_reason", "a refusal must say why")
        attributed = reason in self.declared_reasons
        return self.record(
            1.0 if attributed else 0.0,
            {"reason": reason, "attributed": attributed, **(metadata or {})},
        )

    def unexplained(self) -> tuple[tuple[str, int], ...]:
        """Reasons in the window that no declared rule covers, with counts."""
        counts = Counter(
            str(v.metadata.get("reason"))
            for v in self.values_in_window()
            if not v.metadata.get("attributed", False)
        )
        return tuple(sorted(counts.items()))

    def by_reason(self) -> tuple[tuple[str, int], ...]:
        counts = Counter(str(v.metadata.get("reason")) for v in self.values_in_window())
        return tuple(sorted(counts.items()))

    def unused_rules(self) -> tuple[str, ...]:
        """Declared reasons that never fired in the window."""
        seen = {str(v.metadata.get("reason")) for v in self.values_in_window()}
        return tuple(sorted(self.declared_reasons - seen))

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base.update(
            declared_reasons=len(self.declared_reasons),
            unexplained=self.unexplained(),
            unused_rules=self.unused_rules(),
        )
        return base

    def collect(self) -> SLIValue:
        values = self.values_in_window()
        if not values:
            return self.record(1.0, {"reason": "no refusals", "attributed": True})
        return values[-1]


__all__ = ["AttributionRejected", "RefusalAttribution"]
