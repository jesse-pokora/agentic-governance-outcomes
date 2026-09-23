#!/usr/bin/env python3
"""Measure the enforcement outcomes of a real catalog of gates.

    python harness/measure_primitives.py [path-to-agentic-governance-primitives]

The sibling repository, `agentic-governance-primitives`, is 59 gates whose demo
recordings hold every allow and refuse decision those gates actually produced,
with the reason each gave. That is real enforcement data from real code, which
is why this harness exists and why it does not generate its own.

**It is not production traffic, and every number below describes a test
corpus.** A refusal rate over demo recordings measures how a catalog chose to
demonstrate itself. The instrument is what is being exercised here; the data is
real enough to exercise it honestly and not real enough to mean anything
operational. Saying that once, loudly, is cheaper than a reader inferring it
later.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "outcomes"))

from attribution import attribute  # noqa: E402
from decision import Decision, Observation  # noqa: E402
from denominator import DenominatorRejected, reconcile  # noqa: E402
from rate import Measurement, evaluate  # noqa: E402

DEFAULT_SOURCE = HERE.parents[1] / "agent-governance-apps"


def load(primitives_root: Path) -> Observation:
    """Read every recorded decision out of the sibling catalog."""
    decisions: list[Decision] = []
    tick = 0

    recordings = sorted(primitives_root.glob("apps/*/demo.json")) + sorted(
        primitives_root.glob("compositions/*/demo.json")
    )
    if not recordings:
        raise SystemExit(f"no recordings under {primitives_root}")

    for recording in recordings:
        trace = json.loads(recording.read_text(encoding="utf-8"))
        gate = trace["app"]
        for step in trace["steps"]:
            tick += 1
            if step["outcome"] == "allowed":
                decisions.append(Decision(gate, "allowed", at=tick))
            else:
                decisions.append(
                    Decision(gate, "refused", step["reason"] or "unstated", at=tick)
                )

    # Every request in this corpus produced a decision, because a recorded step
    # *is* a decision. A real gate would supply this count from its own
    # instrumentation, and the two would not always agree.
    return Observation(tuple(decisions), len(decisions), str(primitives_root.name))


def main(argv: list[str]) -> int:
    root = Path(argv[0]).resolve() if argv else DEFAULT_SOURCE
    observation = load(root)

    print(f"source: {observation.source}")
    print(f"gates: {len(observation.gates())}")
    print(f"decisions: {len(observation.decisions)} "
          f"({len(observation.allowances())} allowed, "
          f"{len(observation.refusals())} refused)\n")

    denominator = reconcile(observation)

    measurement = Measurement(
        name="refusal_rate",
        window_ticks=len(observation.decisions),
        minimum_sample=30,
        budget=Decimal("0.60"),
    )
    result = evaluate(measurement, len(observation.refusals()), denominator)
    rate = "n/a" if result.rate is None else f"{result.rate:.3f}"
    print(f"{result.name}: {rate} ({result.numerator}/{result.denominator}) "
          f"-> {result.status}, budget {result.budget}")

    # Every reason any gate in the catalog actually gave. A real deployment
    # would declare this vocabulary up front; here it is harvested, which is
    # exactly the weaker position and is worth seeing stated.
    declared = {d.reason for d in observation.refusals()}
    attribution = attribute(observation, declared)
    print(f"\nrefusal reasons: {len(attribution.by_reason)} distinct, "
          f"{attribution.attributed} attributed, "
          f"{len(attribution.unexplained)} unexplained")

    print("\nmost frequent refusals:")
    for reason, count in sorted(attribution.by_reason, key=lambda p: -p[1])[:8]:
        print(f"  {count:>3}  {reason}")

    print("\nA refusal rate over demo recordings measures how a catalog chose "
          "to demonstrate\nitself, not how a system behaves. The instrument is "
          "what was exercised here.")

    # Demonstrate the denominator check against the case it exists for: a
    # source that saw more requests than it produced decisions for.
    leaky = Observation(observation.decisions, len(observation.decisions) + 12, "leaky")
    try:
        reconcile(leaky)
    except DenominatorRejected as refusal:
        print(f"\nwith 12 requests unaccounted for: {refusal.reason} "
              f"-- {refusal.detail}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
