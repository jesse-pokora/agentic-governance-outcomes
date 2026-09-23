"""The finding, as a test.

`PolicyCompliance.compliance()` depends on the order the checks arrived in.
`CheckPassRate.compliance()` does not. Both are asserted here so the claim can
be re-run rather than believed, and so it fails loudly if the upstream
behaviour changes.

Skips cleanly when `agent_sre` is not installed: the claim is about the real
implementation, and asserting it against a local stand-in would prove nothing.
"""

import sys
import unittest
from itertools import permutations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "outcomes"))

from agt import USING_AGENT_SRE  # noqa: E402
from check_pass_rate import CheckPassRate  # noqa: E402

# Nine passes and one failure. The pass rate is 0.9 in every arrangement.
NINE_AND_ONE = [True] * 9 + [False]


def policy_compliance_over(order):
    from agent_sre.slo.indicators import PolicyCompliance

    sli = PolicyCompliance()
    for compliant in order:
        sli.record_check(compliant)
    return sli


def pass_rate_over(order):
    sli = CheckPassRate()
    for compliant in order:
        sli.record_check(compliant)
    return sli


@unittest.skipUnless(USING_AGENT_SRE, "requires the real agent_sre package")
class PolicyComplianceIsOrderDependentTests(unittest.TestCase):
    def test_the_same_checks_in_two_orders_report_different_compliance(self):
        failure_last = policy_compliance_over(NINE_AND_ONE).compliance()
        failure_first = policy_compliance_over(list(reversed(NINE_AND_ONE))).compliance()

        self.assertEqual(failure_last, 0.9)
        self.assertEqual(failure_first, 0.0)

    def test_the_underlying_pass_rate_is_the_same_in_both(self):
        for order in (NINE_AND_ONE, list(reversed(NINE_AND_ONE))):
            sli = policy_compliance_over(order)
            self.assertAlmostEqual(sli._compliant / sli._total, 0.9)

    def test_it_records_a_running_rate_rather_than_the_check(self):
        sli = policy_compliance_over([True, False])
        recorded = [v.value for v in sli.values_in_window()]

        # 1/1 then 1/2 -- the story so far, not the two outcomes.
        self.assertEqual(recorded, [1.0, 0.5])

    def test_the_base_contract_is_honoured_even_so(self):
        # compliance() really is "fraction of measurements meeting target".
        # The surprise is in what gets recorded as a measurement.
        sli = policy_compliance_over(NINE_AND_ONE)
        values = sli.values_in_window()
        at_target = sum(1 for v in values if v.value >= sli.target)

        self.assertEqual(sli.compliance(), at_target / len(values))


class CheckPassRateIsNotOrderDependentTests(unittest.TestCase):
    def test_every_arrangement_of_the_same_checks_agrees(self):
        results = {
            pass_rate_over(list(order)).compliance()
            for order in set(permutations(NINE_AND_ONE))
        }

        self.assertEqual(results, {0.9})

    def test_it_reports_the_pass_rate_itself(self):
        sli = pass_rate_over(NINE_AND_ONE)

        self.assertEqual(sli.compliance(), 0.9)
        self.assertEqual((sli.passed(), sli.checked()), (9, 10))

    def test_all_passing_and_all_failing(self):
        self.assertEqual(pass_rate_over([True] * 5).compliance(), 1.0)
        self.assertEqual(pass_rate_over([False] * 5).compliance(), 0.0)

    def test_an_empty_window_still_returns_none(self):
        self.assertIsNone(CheckPassRate().compliance())


if __name__ == "__main__":
    unittest.main()
