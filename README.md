# Agentic Governance Outcomes

**Measuring what enforcement actually did.** Not whether a gate exists, and not
whether it refuses correctly in a test — how often it refused in practice, how
many of those refusals were wrong, and what it cost.

Sibling to
[agentic-governance-primitives](https://github.com/jesse-pokora/agentic-governance-primitives),
which demonstrates the gates. This repository measures their outcomes, and the
two are deliberately separate because they need different things to be true:
a demonstration needs a fixture, a measurement needs traffic.

## The four jobs, and which one this is

| Job | What it means | Where |
|---|---|---|
| **Enforce** | The gate refuses. The effect does not happen. | primitives |
| **Attest** | What happened is provable and tamper-evident. | primitives |
| **Measure outcomes** | How often it refused, how many were wrong, what it cost. | **here** |
| **Audit the claim** | Is the report about all of the above trustworthy? | primitives, v1.5 |

A governance suite that only does the first two can tell you a control exists
and cannot tell you whether it is doing anything. A rate is what closes that,
and a rate is a much easier number to produce than to trust.

## The thesis: a rate is easy to compute and hard to trust

Everything here is about what has to be true *before* a number means anything.
Four preconditions, each with a module, each refusing rather than reporting
when it is not met:

**The denominator has to be known.** Refusals are easy to count — every one
emits an event. Requests are not: anything that bypassed the gate, crashed
before reaching it, or was dropped in between leaves no decision behind. So the
request count is supplied by the source and *reconciled* against the decisions
recorded. When they disagree, some requests reached no gate, and the rate
understates by an unknown amount. `denominator.py` refuses to produce a
denominator rather than report that number.

The comfortable failure is a refusal rate that looks reassuringly low precisely
because the unchecked requests were missing from the denominator too.

**Every refusal has to be attributable.** A gate that refuses for a reason
nobody declared has a bug, not a data point, and counting it produces a number
that is partly policy and partly defect with no way to separate them.
`attribution.py` reconciles reasons against the declared vocabulary and reports
unknown ones as a defect list rather than folding them into the numerator.

It also reports **declared rules that never fired** — not a defect, but the
question worth asking: is the rule guarding something that does not happen, or
has the case that triggers it never been exercised?

**The window, the sample floor and the budget have to be fixed first.** All
three get set after seeing the number, routinely. A window chosen afterwards
can make almost any rate; a threshold chosen afterwards is a description, not a
threshold. `Measurement` is frozen at construction, and below the minimum
sample `rate.py` returns `insufficient_sample` **instead of a percentage** —
because one refusal in three requests is 33%, and a number with a caveat
attached gets quoted without the caveat.

**A decision has to know its own provenance.** `Decision` refuses to exist
without a gate and, for a refusal, without a reason.

## Try it on real data

```bash
python -m unittest discover -s tests -p 'test_*.py'
python harness/measure_primitives.py [path-to-primitives-repo]
```

The harness reads the sibling catalog's demo recordings: **319 real allow and
refuse decisions from 60 gates**, each with the reason that gate actually gave.
That is real enforcement data produced by real code, which is why this repo
measures it instead of generating its own events.

```
gates: 60
decisions: 319 (144 allowed, 175 refused)
refusal_rate: 0.549 (175/319) -> within_budget, budget 0.60
refusal reasons: 131 distinct, 175 attributed, 0 unexplained
```

## What that number is not

**It is not production traffic, and 0.549 describes a test corpus.** A refusal
rate over demo recordings measures how a catalog chose to demonstrate itself —
those recordings over-represent refusals on purpose, because refusals are what
the demonstrations are about. The instrument is what is being exercised there;
the data is real enough to exercise it honestly and not real enough to mean
anything operational.

This limit is structural rather than a gap to close. Row three needs a gate
that sees real requests at real volume, so the honest form of this repository
is **an instrument plus the preconditions it enforces**, ready to be pointed at
traffic that exists. Generating synthetic traffic to produce a more impressive
number would measure the generator.

## Status

Early. Four modules, 21 tests, one harness against a real corpus. Not yet
covered: latency cost of a gate, fail-open detection, false-refusal
classification (which needs a labelled ground truth), and anything
longitudinal.

MIT licensed. Built with Claude (Anthropic) as a pair; every commit carries the
co-authorship.
