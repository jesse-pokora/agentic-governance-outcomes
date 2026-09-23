import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "outcomes"))

from agt import SLI, SLIRegistry, SLIValue, TimeWindow  # noqa: E402
from gate_coverage import CoverageRejected, GateCoverage  # noqa: E402
from refusal_attribution import AttributionRejected, RefusalAttribution  # noqa: E402
from registry import register, register_guarded  # noqa: E402
from sample_floor import (  # noqa: E402
    SampleFloorMixin,
    SampleFloorRejected,
    with_sample_floor,
)

DECLARED = {"capability_not_granted", "outside_scope", "host_not_allowed"}


class Compliance(SLI):
    """Stands in for a built-in rate SLI: 1.0 good, 0.0 bad."""

    def __init__(self, name="policy_compliance", target=1.0, window=TimeWindow.DAY_1,
                 **kwargs):
        super().__init__(name=name, target=target, window=window, **kwargs)

    def record_check(self, compliant: bool):
        return self.record(1.0 if compliant else 0.0)

    def collect(self):
        return self.record(1.0)


class ContractTests(unittest.TestCase):
    def test_the_base_reports_compliance_from_a_single_measurement(self):
        # The behaviour the sample floor exists to qualify, asserted here so
        # the extension's reason for existing is visible rather than claimed.
        sli = Compliance()
        sli.record_check(True)

        self.assertEqual(sli.compliance(), 1.0)
        self.assertEqual(sli.to_dict()["measurement_count"], 1)

    def test_an_empty_window_already_yields_none(self):
        # Which is why the floor also returns None: consumers handle it today.
        self.assertIsNone(Compliance().compliance())


class SampleFloorTests(unittest.TestCase):
    def setUp(self):
        self.Guarded = with_sample_floor(Compliance, minimum_sample=30)

    def test_below_the_floor_compliance_is_withheld(self):
        sli = self.Guarded()
        for _ in range(29):
            sli.record_check(True)

        self.assertIsNone(sli.compliance())
        self.assertFalse(sli.sufficient_sample())

    def test_at_the_floor_compliance_is_reported(self):
        sli = self.Guarded()
        for _ in range(30):
            sli.record_check(True)

        self.assertEqual(sli.compliance(), 1.0)
        self.assertTrue(sli.sufficient_sample())

    def test_the_floored_value_matches_the_unfloored_one_once_sufficient(self):
        guarded, plain = self.Guarded(), Compliance()
        for i in range(40):
            guarded.record_check(i % 4 != 0)
            plain.record_check(i % 4 != 0)

        self.assertEqual(guarded.compliance(), plain.compliance())

    def test_to_dict_keeps_every_key_the_base_contract_promises(self):
        sli = self.Guarded()
        sli.record_check(True)
        keys = set(sli.to_dict())

        self.assertTrue(set(Compliance().to_dict()) <= keys)
        self.assertIn("sufficient_sample", keys)
        self.assertIn("minimum_sample", keys)

    def test_a_guarded_type_is_still_the_type_it_wraps(self):
        self.assertTrue(issubclass(self.Guarded, Compliance))
        self.assertTrue(issubclass(self.Guarded, SampleFloorMixin))

    def test_a_floor_below_one_is_refused(self):
        with self.assertRaises(SampleFloorRejected) as ctx:
            with_sample_floor(Compliance, 0)()

        self.assertEqual(ctx.exception.reason, "invalid_minimum_sample")

    def test_the_floor_is_fixed_at_construction(self):
        sli = self.Guarded()
        self.assertEqual(sli.minimum_sample, 30)
        with self.assertRaises(AttributeError):
            sli.minimum_sample = 1


class GateCoverageTests(unittest.TestCase):
    def test_full_coverage_records_one(self):
        sli = GateCoverage()
        sli.record_interval(requests_issued=100, decisions_recorded=100)

        self.assertEqual(sli.current_value(), 1.0)
        self.assertEqual(sli.compliance(), 1.0)

    def test_requests_that_reached_no_gate_drag_coverage_down(self):
        sli = GateCoverage()
        sli.record_interval(requests_issued=100, decisions_recorded=70)

        self.assertAlmostEqual(sli.current_value(), 0.7)
        self.assertEqual(sli.compliance(), 0.0)  # below a target of 1.0
        self.assertEqual(sli.undecided_requests(), 30)

    def test_coverage_is_the_number_that_qualifies_a_perfect_compliance(self):
        # 70 checks, all compliant, 30 requests that reached no gate.
        compliance, coverage = Compliance(), GateCoverage()
        for _ in range(70):
            compliance.record_check(True)
        coverage.record_interval(requests_issued=100, decisions_recorded=70)

        self.assertEqual(compliance.compliance(), 1.0)
        self.assertLess(coverage.current_value(), 1.0)

    def test_more_decisions_than_requests_is_refused(self):
        with self.assertRaises(CoverageRejected) as ctx:
            GateCoverage().record_interval(requests_issued=10, decisions_recorded=11)

        self.assertEqual(ctx.exception.reason, "more_decisions_than_requests")

    def test_an_idle_interval_is_not_full_coverage(self):
        with self.assertRaises(CoverageRejected) as ctx:
            GateCoverage().record_interval(requests_issued=0, decisions_recorded=0)

        self.assertEqual(ctx.exception.reason, "no_requests")

    def test_negative_counts_are_refused(self):
        with self.assertRaises(CoverageRejected) as ctx:
            GateCoverage().record_interval(requests_issued=-1, decisions_recorded=0)

        self.assertEqual(ctx.exception.reason, "negative_count")

    def test_it_serializes_through_the_base_contract(self):
        sli = GateCoverage()
        sli.record_interval(requests_issued=10, decisions_recorded=10)
        payload = sli.to_dict()

        self.assertEqual(payload["name"], "gate_coverage")
        self.assertEqual(payload["window"], "24h")
        self.assertEqual(payload["measurement_count"], 1)


class RefusalAttributionTests(unittest.TestCase):
    def test_declared_reasons_attribute(self):
        sli = RefusalAttribution(DECLARED)
        for _ in range(4):
            sli.record_refusal("capability_not_granted")

        self.assertEqual(sli.compliance(), 1.0)
        self.assertEqual(sli.unexplained(), ())

    def test_an_undeclared_reason_is_a_defect_not_a_data_point(self):
        sli = RefusalAttribution(DECLARED)
        sli.record_refusal("capability_not_granted")
        sli.record_refusal("TypeError")

        self.assertEqual(sli.compliance(), 0.5)
        self.assertEqual(sli.unexplained(), (("TypeError", 1),))

    def test_rules_that_never_fired_are_reported(self):
        sli = RefusalAttribution(DECLARED)
        sli.record_refusal("outside_scope")

        self.assertEqual(sli.unused_rules(), ("capability_not_granted", "host_not_allowed"))

    def test_a_refusal_must_state_a_reason(self):
        with self.assertRaises(AttributionRejected) as ctx:
            RefusalAttribution(DECLARED).record_refusal("")

        self.assertEqual(ctx.exception.reason, "unstated_reason")

    def test_an_empty_vocabulary_is_refused(self):
        with self.assertRaises(AttributionRejected) as ctx:
            RefusalAttribution(set())

        self.assertEqual(ctx.exception.reason, "no_declared_reasons")

    def test_the_breakdown_is_in_a_fixed_order(self):
        def build():
            sli = RefusalAttribution(DECLARED)
            sli.record_refusal("outside_scope")
            sli.record_refusal("capability_not_granted")
            return sli.by_reason()

        self.assertEqual(build(), build())


class RegistryTests(unittest.TestCase):
    def test_the_extension_types_register(self):
        registry = SLIRegistry()
        names = register(registry)

        self.assertEqual(names, ("GateCoverage", "RefusalAttribution"))
        self.assertIsNotNone(registry.get_type("GateCoverage"))

    def test_registering_adds_rather_than_replaces(self):
        registry = SLIRegistry()
        before = set(registry.list_types())
        register(registry)

        self.assertTrue(before <= set(registry.list_types()))

    def test_a_guarded_built_in_registers_alongside_the_original(self):
        registry = SLIRegistry()
        registry.register_type(Compliance)
        name = register_guarded(registry, Compliance, minimum_sample=50)

        self.assertIsNotNone(registry.get_type("Compliance"))
        self.assertIsNotNone(registry.get_type(name))
        self.assertNotEqual(name, "Compliance")


if __name__ == "__main__":
    unittest.main()
