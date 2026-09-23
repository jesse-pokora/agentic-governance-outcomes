"""A rate with an unknown denominator is not a rate.

Refusals are easy to count: every one produces an event. Requests are not —
anything that bypassed the gate, crashed before reaching it, or was dropped
between the caller and the check leaves no decision behind.

So the denominator is supplied by the source and then *reconciled* against the
decisions actually recorded. If they disagree, some requests reached no gate,
and every rate computed from that set is wrong in an unknown direction. That is
refused rather than reported.

The comfortable failure here is a refusal rate that looks reassuringly low
because the requests that went unchecked were never in the denominator either.
"""

from __future__ import annotations

from dataclasses import dataclass

from decision import Observation


class DenominatorRejected(Exception):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class Denominator:
    requests: int
    decided: int
    source: str


def reconcile(observation: Observation) -> Denominator:
    """Establish a denominator, or refuse to produce one.

    `requests_seen = None` means the source could not say how many requests
    there were. That is not zero and it is not "assume it equals the decisions
    we have" — it is an unknown, and it is the shape most instrumentation
    actually arrives in.
    """
    decided = len(observation.decisions)

    if observation.requests_seen is None:
        raise DenominatorRejected(
            "denominator_unknown",
            f"{observation.source} recorded {decided} decisions and cannot say "
            f"how many requests it saw",
        )
    if observation.requests_seen < 0:
        raise DenominatorRejected("invalid_denominator", str(observation.requests_seen))

    if observation.requests_seen < decided:
        # More decisions than requests: the same request was decided twice, or
        # decisions leaked in from another source.
        raise DenominatorRejected(
            "more_decisions_than_requests",
            f"{decided} decisions, {observation.requests_seen} requests",
        )

    undecided = observation.requests_seen - decided
    if undecided:
        # The dangerous direction. These requests reached no gate, so they are
        # missing from the numerator too, and the rate understates by an
        # unknown amount.
        raise DenominatorRejected(
            "requests_reached_no_gate",
            f"{undecided} of {observation.requests_seen} requests produced no "
            f"decision",
        )

    return Denominator(
        requests=observation.requests_seen, decided=decided, source=observation.source
    )
