"""Register these SLIs with an Agent SRE Governance registry.

Section 4.8 says custom SLI types MAY be registered at runtime. That is the
whole integration surface: these are additional SLI types, not a replacement
for anything, and nothing built in changes behaviour because they exist.

    from agent_sre.slo.indicators import SLIRegistry
    from outcomes.registry import register

    registry = SLIRegistry()
    register(registry)
"""

from __future__ import annotations

from agt import SLIRegistry
from gate_coverage import GateCoverage
from refusal_attribution import RefusalAttribution
from sample_floor import with_sample_floor

#: The SLIs this package adds. Each one measures whether some *other*
#: measurement can be believed, which is why they are additions rather than
#: substitutes.
EXTENSION_TYPES = (GateCoverage, RefusalAttribution)


def register(registry: SLIRegistry) -> tuple[str, ...]:
    """Add these SLI types to a registry. Returns the names registered."""
    for sli_class in EXTENSION_TYPES:
        registry.register_type(sli_class)
    return tuple(cls.__name__ for cls in EXTENSION_TYPES)


def register_guarded(
    registry: SLIRegistry, sli_class: type, minimum_sample: int = 30
) -> str:
    """Register a sample-floored variant of an existing SLI type.

    Intended for the built-ins: a sample-floored `PolicyCompliance` registers
    alongside the original rather than replacing it, so adopting the guard is a
    choice made per deployment instead of a change forced on everyone.
    """
    guarded = with_sample_floor(sli_class, minimum_sample)
    registry.register_type(guarded)
    return guarded.__name__


__all__ = ["EXTENSION_TYPES", "register", "register_guarded"]
