import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "outcomes"))

from attribution import AttributionRejected, attribute  # noqa: E402
from decision import Decision, DecisionRejected, Observation  # noqa: E402
from denominator import DenominatorRejected, reconcile  # noqa: E402
from rate import Measurement, RateRejected, evaluate  # noqa: E402

DECLARED = {"capability_not_granted", "outside_scope", "host_not_allowed"}


def observed(decisions, requests_seen, source="toy-gate"):
    return Observation(tuple(decisions), requests_seen, source)


def refusals(n, reason="capability_not_granted", gate="toy-gate"):
    return [Decision(gate, "refused", reason, at=i) for i in range(n)]


def allowances(n, gate="toy-gate"):
    return [Decision(gate, "allowed", at=i) for i in range(n)]


class DecisionTests(unittest.TestCase):
    def test_a_refusal_must_carry_a_reason(self):
        with self.assertRaises(DecisionRejected) as ctx:
            Decision("toy-gate", "refused")

        self.assertEqual(ctx.exception.reason, "unexplained_refusal")

    def test_an_allowance_must_not_carry_one(self):
        with self.assertRaises(DecisionRejected) as ctx:
            Decision("toy-gate", "allowed", "because")

        self.assertEqual(ctx.exception.reason, "allowed_with_reason")

    def test_a_decision_must_name_its_gate(self):
        with self.assertRaises(DecisionRejected) as ctx:
            Decision("", "allowed")

        self.assertEqual(ctx.exception.reason, "unattributed_decision")

    def test_an_unknown_outcome_is_refused(self):
        with self.assertRaises(DecisionRejected) as ctx:
            Decision("toy-gate", "probably fine")

        self.assertEqual(ctx.exception.reason, "unknown_outcome")


class DenominatorTests(unittest.TestCase):
    def test_a_matched_count_reconciles(self):
        denominator = reconcile(observed(refusals(3) + allowances(7), 10))

        self.assertEqual((denominator.requests, denominator.decided), (10, 10))

    def test_an_unknown_request_count_refuses_to_produce_a_denominator(self):
        with self.assertRaises(DenominatorRejected) as ctx:
            reconcile(observed(refusals(3), None))

        self.assertEqual(ctx.exception.reason, "denominator_unknown")

    def test_requests_that_reached_no_gate_are_refused(self):
        # The dangerous direction: those requests are missing from the
        # numerator too, so the rate understates by an unknown amount.
        with self.assertRaises(DenominatorRejected) as ctx:
            reconcile(observed(refusals(2) + allowances(3), 10))

        self.assertEqual(ctx.exception.reason, "requests_reached_no_gate")
        self.assertIn("5 of 10", ctx.exception.detail)

    def test_more_decisions_than_requests_is_refused(self):
        with self.assertRaises(DenominatorRejected) as ctx:
            reconcile(observed(refusals(5), 3))

        self.assertEqual(ctx.exception.reason, "more_decisions_than_requests")

    def test_a_negative_request_count_is_refused(self):
        with self.assertRaises(DenominatorRejected) as ctx:
            reconcile(observed(refusals(1), -1))

        self.assertEqual(ctx.exception.reason, "invalid_denominator")


class RateTests(unittest.TestCase):
    def setUp(self):
        self.measurement = Measurement(
            name="refusal_rate", window_ticks=100, minimum_sample=30,
            budget=Decimal("0.10"),
        )

    def test_a_rate_within_budget(self):
        denominator = reconcile(observed(refusals(2) + allowances(98), 100))
        result = evaluate(self.measurement, 2, denominator)

        self.assertEqual(result.status, "within_budget")
        self.assertEqual(result.rate, Decimal("0.02"))

    def test_a_rate_over_budget(self):
        denominator = reconcile(observed(refusals(20) + allowances(80), 100))
        result = evaluate(self.measurement, 20, denominator)

        self.assertEqual(result.status, "over_budget")

    def test_below_the_minimum_sample_there_is_no_rate_at_all(self):
        # One refusal in three requests is 33%, and quoting it as such is
        # worse than saying nothing.
        denominator = reconcile(observed(refusals(1) + allowances(2), 3))
        result = evaluate(self.measurement, 1, denominator)

        self.assertEqual(result.status, "insufficient_sample")
        self.assertIsNone(result.rate)
        self.assertEqual(result.denominator, 3)

    def test_the_budget_is_declared_before_measuring_and_frozen(self):
        with self.assertRaises(Exception):
            self.measurement.budget = Decimal("0.99")

    def test_a_budget_outside_zero_to_one_is_refused(self):
        with self.assertRaises(RateRejected) as ctx:
            Measurement("r", 100, 30, Decimal("1.5"))

        self.assertEqual(ctx.exception.reason, "budget_out_of_range")

    def test_a_window_of_zero_is_refused(self):
        with self.assertRaises(RateRejected) as ctx:
            Measurement("r", 0, 30, Decimal("0.1"))

        self.assertEqual(ctx.exception.reason, "invalid_window")

    def test_a_numerator_larger_than_the_denominator_is_refused(self):
        denominator = reconcile(observed(refusals(30) + allowances(70), 100))

        with self.assertRaises(RateRejected) as ctx:
            evaluate(self.measurement, 101, denominator)

        self.assertEqual(ctx.exception.reason, "numerator_exceeds_denominator")


class AttributionTests(unittest.TestCase):
    def test_refusals_matching_declared_reasons_are_attributed(self):
        result = attribute(observed(refusals(4), 4), DECLARED)

        self.assertTrue(result.clean)
        self.assertEqual(result.attributed, 4)

    def test_a_reason_nobody_declared_is_a_defect_not_a_data_point(self):
        mixed = refusals(3) + [Decision("toy-gate", "refused", "TypeError", at=9)]
        result = attribute(observed(mixed, 4), DECLARED)

        self.assertFalse(result.clean)
        self.assertEqual(result.unexplained, (("TypeError", 1),))
        self.assertEqual(result.attributed, 3)

    def test_declared_rules_that_never_fired_are_reported(self):
        result = attribute(observed(refusals(2), 2), DECLARED)

        self.assertEqual(result.unused_rules, ("host_not_allowed", "outside_scope"))

    def test_an_empty_vocabulary_is_refused(self):
        with self.assertRaises(AttributionRejected) as ctx:
            attribute(observed(refusals(1), 1), set())

        self.assertEqual(ctx.exception.reason, "no_declared_reasons")

    def test_the_breakdown_is_in_a_fixed_order(self):
        first = attribute(observed(refusals(2), 2), DECLARED)
        second = attribute(observed(refusals(2), 2), DECLARED)

        self.assertEqual(first.by_reason, second.by_reason)


if __name__ == "__main__":
    unittest.main()
