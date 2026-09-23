"""The unit of measurement: one enforcement decision.

A gate either let something through or refused it. That event, with the rule
that decided and the reason it gave, is the only thing everything else here is
computed from.

The type is deliberately narrow. A decision that cannot say which gate made it
or why cannot be counted, because a rate assembled from events that do not know
their own provenance is a number with nothing behind it.
"""

from __future__ import annotations

from dataclasses import dataclass

OUTCOMES = frozenset({"allowed", "refused"})


class DecisionRejected(Exception):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class Decision:
    """One gate, one request, one outcome."""

    gate: str
    outcome: str
    reason: str = ""
    at: int = 0  # monotonic tick; the source supplies it, this module never invents one

    def __post_init__(self) -> None:
        if not self.gate:
            raise DecisionRejected("unattributed_decision", "no gate named")
        if self.outcome not in OUTCOMES:
            raise DecisionRejected("unknown_outcome", self.outcome)
        if self.outcome == "refused" and not self.reason:
            # A refusal with no reason cannot be attributed to a rule, which
            # makes it impossible to tell a correct refusal from a bug.
            raise DecisionRejected("unexplained_refusal", self.gate)
        if self.outcome == "allowed" and self.reason:
            raise DecisionRejected(
                "allowed_with_reason", f"{self.gate}: {self.reason}"
            )
        if self.at < 0:
            raise DecisionRejected("invalid_time", str(self.at))


@dataclass(frozen=True)
class Observation:
    """A set of decisions, and how many requests the source says it saw.

    `requests_seen` is supplied by whatever produced the decisions, not counted
    from them. The two are compared rather than assumed equal — see
    `denominator.py` for why that difference is the whole point.
    """

    decisions: tuple[Decision, ...]
    requests_seen: int | None
    source: str

    def refusals(self) -> tuple[Decision, ...]:
        return tuple(d for d in self.decisions if d.outcome == "refused")

    def allowances(self) -> tuple[Decision, ...]:
        return tuple(d for d in self.decisions if d.outcome == "allowed")

    def gates(self) -> tuple[str, ...]:
        return tuple(sorted({d.gate for d in self.decisions}))
