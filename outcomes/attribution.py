"""Every refusal must be explained by a rule that was declared.

A gate that refuses for a reason nobody declared has a bug, not a data point.
Counting that refusal alongside the intended ones produces a rate that is
partly a measure of policy and partly a measure of a defect, with no way to
tell how much of each.

So refusal reasons are reconciled against the declared rule vocabulary before
any rate is computed. Unknown reasons are reported as a defect list, not folded
into the numerator.

This is the outcome-side counterpart of the fixed denial vocabularies in the
primitives catalog: there, a gate declares the reasons it can give; here, the
measurement checks that it only gave those.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from decision import Observation


class AttributionRejected(Exception):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class Attribution:
    attributed: int
    unexplained: tuple[tuple[str, int], ...]  # (reason, count), fixed order
    by_reason: tuple[tuple[str, int], ...]
    unused_rules: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return not self.unexplained


def attribute(observation: Observation, declared_reasons: set[str]) -> Attribution:
    """Match every refusal to a declared reason.

    `unused_rules` is reported as well: a declared reason that never fired is
    not a defect, but it is the question worth asking — either the rule is
    guarding something that does not happen, or the case that would trigger it
    has never been exercised.
    """
    if not declared_reasons:
        raise AttributionRejected(
            "no_declared_reasons",
            "a refusal vocabulary of nothing explains nothing",
        )

    counts = Counter(d.reason for d in observation.refusals())
    unexplained = tuple(
        sorted((r, n) for r, n in counts.items() if r not in declared_reasons)
    )
    attributed = sum(n for r, n in counts.items() if r in declared_reasons)

    return Attribution(
        attributed=attributed,
        unexplained=unexplained,
        by_reason=tuple(sorted(counts.items())),
        unused_rules=tuple(sorted(declared_reasons - set(counts))),
    )
