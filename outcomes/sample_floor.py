"""Withhold a compliance figure that rests on too few measurements.

`SLI.compliance()` returns `good / len(values)`. With one measurement in the
window that is 1.0, reported identically to 1.0 drawn from thirty thousand.
`to_dict()` does carry `measurement_count`, so the information is present — but
it is present *beside* the number rather than *in* it, and the number is what
gets quoted.

This mixin declares a minimum sample and returns `None` below it.

`None` is chosen deliberately: the base contract already returns `None` from
`compliance()` when the window is empty, and every consumer therefore already
handles it. "Not enough evidence yet" and "no evidence yet" are the same
statement at different sample sizes, so they should not need different
handling.
"""

from __future__ import annotations

from typing import Any

from agt import SLI, TimeWindow


class SampleFloorRejected(Exception):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


class SampleFloorMixin:
    """Mix in ahead of an SLI to gate `compliance()` on a minimum sample.

    Declared at construction and never afterwards, because a floor chosen once
    the number is known is not a floor.
    """

    def __init__(self, *args: Any, minimum_sample: int = 30, **kwargs: Any) -> None:
        if minimum_sample < 1:
            raise SampleFloorRejected("invalid_minimum_sample", str(minimum_sample))
        self._minimum_sample = minimum_sample
        super().__init__(*args, **kwargs)

    @property
    def minimum_sample(self) -> int:
        return self._minimum_sample

    def sufficient_sample(self) -> bool:
        return len(self.values_in_window()) >= self._minimum_sample

    def compliance(self) -> float | None:
        if not self.sufficient_sample():
            return None
        return super().compliance()

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        # Additive only: every key the base contract promises is still present
        # and unchanged, so an existing consumer keeps working.
        base.update(
            minimum_sample=self._minimum_sample,
            sufficient_sample=self.sufficient_sample(),
        )
        return base


def with_sample_floor(sli_class: type[SLI], minimum_sample: int = 30) -> type[SLI]:
    """Build a sample-floored variant of any SLI type, built-in or custom.

        GuardedPolicyCompliance = with_sample_floor(PolicyCompliance, 100)

    The result is a subclass, so it registers, serializes and aggregates
    exactly like the type it wraps.
    """

    guarded = type(
        f"SampleFloored{sli_class.__name__}",
        (SampleFloorMixin, sli_class),
        {"__doc__": f"{sli_class.__name__} that withholds compliance below "
                    f"{minimum_sample} measurements."},
    )
    original_init = guarded.__init__

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("minimum_sample", minimum_sample)
        original_init(self, *args, **kwargs)

    guarded.__init__ = __init__  # type: ignore[method-assign]
    return guarded


__all__ = ["SampleFloorMixin", "SampleFloorRejected", "TimeWindow", "with_sample_floor"]
