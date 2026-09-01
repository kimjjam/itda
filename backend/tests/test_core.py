import unittest

from pydantic import ValidationError

from app.core.risk_signal import detect_risk_signal
from app.core.scoring_engine import score_evidence
from app.models.schemas import ApplicantInput


def applicant(**overrides: object) -> ApplicantInput:
    values: dict[str, object] = {
        "nationality": "베트남",
        "visa_type": "E-9",
        "employment_months": 14,
        "monthly_income_krw": 2_700_000,
        "telecom_paid_months": 12,
        "insurance_paid_months": 8,
        "remittance_monthly_amount": 600_000,
        "remittance_currency": "vnd",
        "remittance_months": 6,
        "document_categories": ["employment", "telecom"],
        "self_reported_risk": False,
    }
    values.update(overrides)
    return ApplicantInput(**values)


class CoreRulesTest(unittest.TestCase):
    def test_scoring_is_deterministic_and_risk_is_separate(self) -> None:
        data = applicant(self_reported_risk=True)
        first = score_evidence(data)
        second = score_evidence(data)

        self.assertEqual(first, second)
        self.assertEqual(data.language, "ko")
        self.assertEqual(first.strength, 72)
        self.assertEqual(first.level, "보통")
        self.assertEqual(len(first.items), 5)
        self.assertTrue(detect_risk_signal(data.self_reported_risk).active)

    def test_self_reported_values_without_documents_are_limited(self) -> None:
        result = score_evidence(applicant(document_categories=[]))

        self.assertEqual(result.strength, 22)
        self.assertTrue(all(item.strength == "limited" for item in result.items))
        self.assertTrue(all("증빙 미제출" in item.source for item in result.items))

    def test_vietnamese_copy_is_localized(self) -> None:
        data = applicant(language="vi", document_categories=[], self_reported_risk=True)
        result = score_evidence(data)
        alert = detect_risk_signal(data.self_reported_risk, data.language)

        self.assertIn("Tính liên tục", result.items[0].title)
        self.assertIn("Tự khai", result.items[0].source)
        self.assertIn("Bạn đã khai báo", alert.message or "")

    def test_input_boundary_rejects_negative_months(self) -> None:
        with self.assertRaises(ValidationError):
            applicant(employment_months=-1)

        with self.assertRaises(ValidationError):
            applicant(remittance_currency="12$")

        with self.assertRaises(ValidationError):
            applicant(language="en")


if __name__ == "__main__":
    unittest.main()
