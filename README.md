# Agentic Governance Outcomes

[![CI](https://github.com/jesse-pokora/agentic-governance-outcomes/actions/workflows/ci.yml/badge.svg)](https://github.com/jesse-pokora/agentic-governance-outcomes/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Four SLIs that make the other SLIs interpretable.** An extension for
[microsoft/agent-governance-toolkit](https://github.com/microsoft/agent-governance-toolkit),
written against *Agent SRE Governance 1.0* section 4 and registered through the
`SLIRegistry` extension point the spec provides.

Nothing here replaces anything. Every built-in keeps its behaviour; these are
additional SLI types that answer a question the built-ins do not: **can the
number beside this one be believed?**

## The gap

`SLI.compliance()` returns `good / len(values)`. Three consequences follow from
that line, and none of them is a bug — they are simply outside what a rate can
express:

**One measurement gives 1.0.** A `policy_compliance` of 1.0 drawn from a single
check is reported exactly like one drawn from thirty thousand. `to_dict()` does
carry `measurement_count`, so the information exists — but it sits *beside* the
number rather than *in* it, and the number is what gets quoted into a slide.

**Requests that bypassed the gate are invisible.** `PolicyCompliance.record_check()`
is called when a check happens. A request that failed before reaching the gate,
or routed around it, never calls it — so it is absent from the numerator and
the denominator alike, and compliance stays perfect. The figure is not wrong
about what it measured; it is silent about what it never saw.

**A policy refusal and an evaluator crash are the same boolean.**
`record_check(compliant=False)` cannot distinguish "the policy said no" from
"the evaluator raised", so the resulting rate is part policy and part defect
with no way to separate them.

## A fourth thing, found by running it

`PolicyCompliance.record_check` records a **running cumulative rate** as each
measurement:

```python
rate = self._compliant / self._total
return self.record(rate, metadata)
```

`compliance()` then reports the fraction of those running rates that met the
target. At a target of 1.0 a running rate is at target only while nothing has
failed yet — so the figure is really *the fraction of the window during which
nothing had failed*, and one early failure holds it near zero however well the
rest of the window goes.

That makes it order-dependent. Same ten checks, nine passing:

| Arrangement | `compliance()` | actual pass rate |
|---|---|---|
| nine passes, then the failure | **0.900** | 0.900 |
| the failure, then nine passes | **0.000** | 0.900 |

`tests/test_order_dependence.py` is that comparison, run against the installed
package so it fails loudly if the upstream behaviour changes.

**This is not a spec violation.** Section 4.1 defines `compliance()` as the
fraction of measurements meeting the target, and it is exactly that — a test
asserts so. The surprise is in what `PolicyCompliance` chooses to record as a
measurement, which the spec does not constrain.

`CheckPassRate` records each check as itself, so `compliance()` is the pass
rate and every permutation agrees. It is an additional view, not a correction:
running both is useful, because a large gap between them says failures are
clustered early in the window.

## What this adds

| SLI | Answers |
|---|---|
| `CheckPassRate` | What fraction of checks passed, independent of the order they arrived in? |
| `GateCoverage` | Of the requests the caller issued, what fraction reached a gate at all? |
| `RefusalAttribution` | What fraction of refusals carry a reason the gate declared it could give? |
| `with_sample_floor(AnySLI, n)` | Withholds `compliance()` below `n` measurements, for any SLI type including the built-ins |

`with_sample_floor` returns **`None`** below the floor, which is deliberate:
the base contract already returns `None` from `compliance()` on an empty
window, so every consumer handles it today. "Not enough evidence yet" and "no
evidence yet" are the same statement at different sample sizes and should not
need different handling.

The result is a subclass, so it registers, serializes and aggregates exactly
like the type it wraps — and it registers *alongside* the original, so adopting
the guard is a per-deployment choice rather than a change forced on everyone.

## Using it

```python
from agent_sre.slo.indicators import PolicyCompliance, SLIRegistry
from outcomes.registry import register, register_guarded

registry = SLIRegistry()
register(registry)                                # CheckPassRate, GateCoverage, RefusalAttribution
register_guarded(registry, PolicyCompliance, 30)      # SampleFlooredPolicyCompliance
```

`outcomes/agt.py` imports the real `SLI`, `SLIValue`, `TimeWindow` and
`SLIRegistry` from `agent_sre` when it is installed, and falls back to a
spec-faithful implementation of section 4 when it is not — so the package is
testable on its own and drop-in when it is not. The fallback exists to keep the
tests honest, not to fork the contract: if the two ever disagree, the installed
implementation is right.

## Seeing it work

```bash
python -m unittest discover -s tests -p 'test_*.py'
python harness/measure_primitives.py [path-to-primitives-repo]
```

The harness reads the sibling catalog
[agentic-governance-primitives](https://github.com/jesse-pokora/agentic-governance-primitives)
— **319 real allow and refuse decisions from 60 gates**, each with the reason
that gate actually gave:

```
built-in, unqualified:
  policy_compliance   0.009  over 319 measurements
                             ^ the fraction of the window during which nothing had failed yet,
                               not the pass rate. See tests/test_order_dependence.py

with this package registered:
  policy_compliance   0.009  (sample floor 30, sufficient=True)
  gate_coverage       1.000  (0 requests reached no gate)
  check_pass_rate     0.451  (144/319 checks passed, order-independent)
  refusal_attribution 1.000  (0 unexplained of 131 distinct reasons)

the same SLI over 1 measurement:
  built-in            would report 1.000
  sample-floored      None  (withheld; 1 < 30)
```

Note what the corpus scores: coverage and attribution both 1.0. That is the
expected result for a catalog whose gates all declare fixed refusal
vocabularies and whose every recorded request produced a decision — the
instrument agreeing with a well-behaved input is how you find out it is wired
up, not evidence that it is useful. The last two lines are where it earns its
place.

That `0.009` is the order-dependence above, on a corpus whose fourth decision
is a refusal: the running rate leaves 1.0 early and never returns. The actual
pass rate is 0.451.

**And none of it is production traffic.** A refusal rate over demo recordings
measures how a catalog chose to demonstrate itself; those recordings
over-represent refusals deliberately. The instrument is what is being
exercised.

## Why it is a separate repository

The sibling catalog demonstrates gates against fixtures. Measuring outcomes
needs traffic. Those are different constraints, so mixing them would force one
of the two to pretend — and the honest form of an outcome measure is an
instrument plus the preconditions it enforces, ready to be pointed at traffic
that exists.

## Status

Early. Four SLIs, 33 tests, one harness against a real corpus. Verified
against the installed `agent-sre` 3.7.0 as well as the fallback: the extension
SLIs subclass the real base, register into a real `SLIRegistry` alongside its
eight built-ins, and the order-dependence finding is reproduced against the
real implementation rather than a stand-in. Not yet
covered: latency cost of a gate, fail-open detection, false-refusal
classification (which needs a labelled ground truth), and anything
longitudinal.

CI installs `agent-sre` unpinned, so the order-dependence test above runs
against whatever the current release is rather than a version frozen here — if
upstream changes the behaviour, the suite is what says so.

Not affiliated with or endorsed by Microsoft. MIT licensed. Built with Claude
(Anthropic) as a pair; every commit carries the co-authorship.
