"""A rate needs a declared window, a minimum sample, and a budget set first.

Three things have to be fixed before the number is computed, and all three are
routinely fixed afterwards instead:

- the **window** it covers, because "the refusal rate" over an unstated period
  can be made to say almost anything by choosing the period;
- the **minimum sample** below which no rate is reported, because 1 refusal in
  3 requests is 33% and means nothing;
- the **budget**, because a threshold chosen after seeing the number is not a
  threshold, it is a description.

So `Measurement` is constructed before measuring and is frozen. Below the
minimum sample this returns `insufficient_sample` rather than a percentage: a
number with a caveat attached gets quoted without the caveat.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from denominator import Denominator


class RateRejected(Exception):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class Measurement:
    """Declared before the first decision is counted."""

    name: str
    window_ticks: int
    minimum_sample: int
    budget: Decimal  # the highest acceptable rate, as a fraction

    def __post_init__(self) -> None:
        if self.window_ticks <= 0:
            raise RateRejected("invalid_window", str(self.window_ticks))
        if self.minimum_sample < 1:
            raise RateRejected("invalid_minimum_sample", str(self.minimum_sample))
        if not (Decimal(0) <= self.budget <= Decimal(1)):
            raise RateRejected("budget_out_of_range", str(self.budget))


@dataclass(frozen=True)
class Result:
    name: str
    status: str  # "within_budget", "over_budget", or "insufficient_sample"
    rate: Decimal | None
    numerator: int
    denominator: int
    budget: Decimal


def evaluate(
    measurement: Measurement, numerator: int, denominator: Denominator
) -> Result:
    """Compute the rate, or decline to.

    `numerator` is the count of the thing being rated — refusals, wrong
    refusals, failures. The denominator arrives already reconciled, so this
    function never has to trust a total it was simply handed.
    """
    if numerator < 0:
        raise RateRejected("invalid_numerator", str(numerator))
    if numerator > denominator.requests:
        raise RateRejected(
            "numerator_exceeds_denominator",
            f"{numerator} of {denominator.requests}",
        )

    if denominator.requests < measurement.minimum_sample:
        # Deliberately no rate at all. One refusal in three requests is 33%,
        # and quoting it as such is worse than saying nothing.
        return Result(
            name=measurement.name,
            status="insufficient_sample",
            rate=None,
            numerator=numerator,
            denominator=denominator.requests,
            budget=measurement.budget,
        )

    rate = Decimal(numerator) / Decimal(denominator.requests)
    status = "within_budget" if rate <= measurement.budget else "over_budget"

    return Result(
        name=measurement.name,
        status=status,
        rate=rate,
        numerator=numerator,
        denominator=denominator.requests,
        budget=measurement.budget,
    )
