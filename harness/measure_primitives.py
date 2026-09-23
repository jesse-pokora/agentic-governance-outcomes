#!/usr/bin/env python3
"""Drive the extension SLIs from a real catalog of gates.

    python harness/measure_primitives.py [path-to-agentic-governance-primitives]

The sibling repository is 59 gates whose demo recordings hold every allow and
refuse decision those gates produced, with the reason each gave. Real output
from real code, which is why this reads it rather than generating events.

**It is not production traffic.** A refusal rate over demo recordings measures
how a catalog chose to demonstrate itself — those recordings over-represent
refusals deliberately, because refusals are the point of a demonstration. What
is being exercised here is the instrument.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "outcomes"))

from agt import SLI, SLIRegistry, TimeWindow, USING_AGENT_SRE  # noqa: E402
from gate_coverage import GateCoverage  # noqa: E402
from refusal_attribution import RefusalAttribution  # noqa: E402
from registry import register, register_guarded  # noqa: E402
from sample_floor import with_sample_floor  # noqa: E402

DEFAULT_SOURCE = HERE.parents[1] / "agent-governance-apps"


class PolicyComplianceStub(SLI):
    """Stands in for `agent_sre`'s PolicyCompliance when it is not installed."""

    def __init__(self, name="policy_compliance", target=1.0, window=TimeWindow.DAY_1):
        super().__init__(name=name, target=target, window=window)

    def record_check(self, compliant: bool):
        return self.record(1.0 if compliant else 0.0)

    def collect(self):
        return self.record(1.0)


def policy_compliance_type() -> type[SLI]:
    if USING_AGENT_SRE:  # pragma: no cover - depends on the environment
        from agent_sre.slo.indicators import PolicyCompliance

        return PolicyCompliance
    return PolicyComplianceStub


def load(primitives_root: Path) -> tuple[list[tuple[str, str, str]], set[str]]:
    """Return (gate, outcome, reason) per decision, and the reason vocabulary."""
    recordings = sorted(primitives_root.glob("apps/*/demo.json")) + sorted(
        primitives_root.glob("compositions/*/demo.json")
    )
    if not recordings:
        raise SystemExit(f"no recordings under {primitives_root}")

    decisions, reasons = [], set()
    for recording in recordings:
        trace = json.loads(recording.read_text(encoding="utf-8"))
        for step in trace["steps"]:
            reason = step["reason"] or "unstated"
            decisions.append((trace["app"], step["outcome"], reason))
            if step["outcome"] == "denied":
                reasons.add(reason)
    return decisions, reasons


def main(argv: list[str]) -> int:
    root = Path(argv[0]).resolve() if argv else DEFAULT_SOURCE
    decisions, declared = load(root)
    refusals = [d for d in decisions if d[1] == "denied"]

    print(f"source: {root.name}")
    print(f"agent_sre installed: {USING_AGENT_SRE}"
          f"{'' if USING_AGENT_SRE else '  (using the spec-faithful fallback)'}")
    print(f"gates: {len({d[0] for d in decisions})}, decisions: {len(decisions)} "
          f"({len(decisions) - len(refusals)} allowed, {len(refusals)} refused)\n")

    PolicyCompliance = policy_compliance_type()
    Guarded = with_sample_floor(PolicyCompliance, minimum_sample=30)

    plain, guarded = PolicyCompliance(), Guarded()
    for _, outcome, _ in decisions:
        compliant = outcome == "allowed"
        plain.record_check(compliant)
        guarded.record_check(compliant)

    coverage = GateCoverage()
    coverage.record_interval(requests_issued=len(decisions),
                             decisions_recorded=len(decisions))

    attribution = RefusalAttribution(declared)
    for _, _, reason in refusals:
        attribution.record_refusal(reason)

    print("built-in, unqualified:")
    print(f"  policy_compliance   {plain.compliance():.3f}  "
          f"over {plain.to_dict()['measurement_count']} measurements")

    print("\nwith this package registered:")
    print(f"  policy_compliance   {guarded.compliance():.3f}  "
          f"(sample floor {guarded.minimum_sample}, "
          f"sufficient={guarded.sufficient_sample()})")
    print(f"  gate_coverage       {coverage.current_value():.3f}  "
          f"({coverage.undecided_requests()} requests reached no gate)")
    print(f"  refusal_attribution {attribution.compliance():.3f}  "
          f"({len(attribution.unexplained())} unexplained of "
          f"{len(attribution.by_reason())} distinct reasons)")

    # The case the guard exists for: a window with almost nothing in it.
    thin = Guarded()
    thin.record_check(True)
    print(f"\nthe same SLI over 1 measurement:")
    print(f"  built-in            {PolicyCompliance().__class__.__name__}"
          f" would report 1.000")
    print(f"  sample-floored      {thin.compliance()}  "
          f"(withheld; {len(thin.values_in_window())} < {thin.minimum_sample})")

    registry = SLIRegistry()
    added = register(registry)
    guarded_name = register_guarded(registry, PolicyCompliance, minimum_sample=30)
    print(f"\nregistered into an SLIRegistry: {', '.join(added + (guarded_name,))}")
    print(f"registry now lists {len(registry.list_types())} SLI types, "
          f"none replaced")

    print("\nA refusal rate over demo recordings measures how a catalog chose to "
          "demonstrate\nitself, not how a system behaves. The instrument is what "
          "was exercised here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
