"""GateCoverage: the fraction of requests that reached a gate at all.

`PolicyCompliance` records a measurement per policy *check*. A request that
bypassed the gate, failed before reaching it, or was dropped between the caller
and the check never calls `record_check`, so it is absent from the numerator
and the denominator alike — and compliance stays at 1.0.

That is the quiet way a compliance figure stays perfect while coverage falls.
The number is not wrong about what it measured; it is silent about what it
never saw.

So this SLI measures the other thing: of the requests the caller says it
issued, what fraction produced a decision. Reported beside `policy_compliance`,
it is the number that makes `policy_compliance` interpretable. Reported without
it, a compliance of 1.0 means "every request we looked at was fine", and the
interesting word is *looked*.
"""

from __future__ import annotations

from typing import Any

from agt import SLI, SLIValue, TimeWindow


class CoverageRejected(Exception):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


class GateCoverage(SLI):
    """Fraction of issued requests that produced a policy decision.

    Target defaults to 1.0: every request should reach a gate. Anything less
    means the compliance figure beside it is computed over a subset of unknown
    shape.
    """

    def __init__(
        self,
        name: str = "gate_coverage",
        target: float = 1.0,
        window: TimeWindow | str = TimeWindow.DAY_1,
        **kwargs: Any,
    ) -> None:
        super().__init__(name=name, target=target, window=window, **kwargs)

    def record_interval(
        self,
        requests_issued: int,
        decisions_recorded: int,
        metadata: dict[str, Any] | None = None,
    ) -> SLIValue:
        """Record one interval's coverage.

        Both counts are supplied by the caller, because only the caller knows
        how many requests it issued. An SLI that derived the denominator from
        the decisions it was given would be assuming the thing it exists to
        check.
        """
        if requests_issued < 0 or decisions_recorded < 0:
            raise CoverageRejected(
                "negative_count", f"{requests_issued}/{decisions_recorded}"
            )
        if decisions_recorded > requests_issued:
            # More decisions than requests: double-counting, or decisions from
            # another source. Either way the pair cannot be a coverage ratio.
            raise CoverageRejected(
                "more_decisions_than_requests",
                f"{decisions_recorded} decisions, {requests_issued} requests",
            )
        if requests_issued == 0:
            # An interval with no traffic is not full coverage, and recording
            # it as 1.0 would let idle intervals inflate the window.
            raise CoverageRejected("no_requests", "an idle interval is not coverage")

        coverage = decisions_recorded / requests_issued
        return self.record(
            coverage,
            {
                "requests_issued": requests_issued,
                "decisions_recorded": decisions_recorded,
                "undecided": requests_issued - decisions_recorded,
                **(metadata or {}),
            },
        )

    def undecided_requests(self) -> int:
        """Total requests in the window that reached no gate."""
        return sum(
            int(v.metadata.get("undecided", 0)) for v in self.values_in_window()
        )

    def collect(self) -> SLIValue:
        """Re-emit the latest coverage, per the base contract."""
        values = self.values_in_window()
        if not values:
            return self.record(0.0, {"reason": "no intervals recorded"})
        return values[-1]


__all__ = ["CoverageRejected", "GateCoverage"]
