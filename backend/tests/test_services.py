import json
from io import BytesIO
import unittest
from unittest.mock import patch

import httpx
import pymupdf
from PIL import Image

from app.core.config import Settings
from app.models.schemas import DataSourceStatus, EvidenceCategory
from app.core.scoring_engine import score_evidence
from app.models.schemas import ApplicantInput
from app.services.exchange_rate_client import ExchangeRateClient
from app.services.kosis_client import KosisClient
from app.services.llm_explainer import LlmExplainer, _document_images


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": "",
        "blob_read_write_token": "",
        "kosis_api_key": "test",
        "exim_exchange_api_key": "test",
        "llm_api_key": "",
        "llm_model": "",
        "llm_api_base_url": "",
        "frontend_origin": "http://localhost:5173",
    }
    values.update(overrides)
    return Settings(**values)


class ExternalServicesTest(unittest.IsolatedAsyncioTestCase):
    async def test_kosis_live_response_is_cached(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(
                200,
                json=[{"TBL_NM": "인구총조사", "DT": "51,000,000", "UNIT_NM": "명", "PRD_DE": "2025"}],
            )

        client = KosisClient(settings(), httpx.MockTransport(handler))
        live = await client.get_population_context()
        cached = await client.get_population_context()

        self.assertEqual(live.status, DataSourceStatus.LIVE)
        self.assertEqual(cached.status, DataSourceStatus.CACHE)
        self.assertEqual(calls, 1)

    async def test_exchange_rate_normalizes_hundred_unit_currency(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[{"result": 1, "cur_unit": "VND(100)", "deal_bas_r": "5.50"}])

        metric = await ExchangeRateClient(settings(), httpx.MockTransport(handler)).get_rate("vnd")

        self.assertEqual(metric.status, DataSourceStatus.LIVE)
        self.assertAlmostEqual(float(metric.value or 0), 0.055)

    async def test_http_200_api_error_falls_back(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            body = {"err": "10", "errMsg": "missing key"}
            return httpx.Response(200, content=json.dumps(body).encode(), headers={"content-type": "application/json"})

        metric = await KosisClient(settings(), httpx.MockTransport(handler)).get_population_context()
        self.assertEqual(metric.status, DataSourceStatus.FALLBACK)

    async def test_llm_explanation_accepts_only_grounded_output(self) -> None:
        data = ApplicantInput(
            nationality="베트남",
            visa_type="E-9",
            employment_months=14,
            monthly_income_krw=2_700_000,
            telecom_paid_months=12,
            insurance_paid_months=8,
            remittance_monthly_amount=600_000,
            remittance_currency="VND",
            remittance_months=6,
        )
        explanations = {
            key: "입력된 기록 범위 안에서 지속성을 확인했습니다."
            for key in ["employment", "telecom", "insurance", "income", "remittance"]
        }

        def handler(request: httpx.Request) -> httpx.Response:
            content = json.dumps(
                {"summary": "제출된 사실만 바탕으로 근거를 정리했습니다.", "explanations": explanations},
                ensure_ascii=False,
            )
            return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

        configured = settings(llm_api_key="test", llm_model="test-model", llm_api_base_url="https://llm.example/v1")
        result = await LlmExplainer(configured, httpx.MockTransport(handler)).explain(
            data,
            score_evidence(data),
            [],
        )
        summary, items = result

        self.assertEqual(summary, "제출된 사실만 바탕으로 근거를 정리했습니다.")
        self.assertEqual(items[0].explanation, explanations["employment"])
        self.assertTrue(result.llm_succeeded)

    async def test_llm_numeric_or_decisive_claim_falls_back(self) -> None:
        data = ApplicantInput(
            nationality="베트남",
            visa_type="E-9",
            employment_months=14,
            monthly_income_krw=2_700_000,
            telecom_paid_months=12,
            insurance_paid_months=8,
            remittance_monthly_amount=600_000,
            remittance_currency="VND",
            remittance_months=6,
        )
        configured = settings(llm_api_key="test", llm_model="test-model", llm_api_base_url="https://llm.example/v1")

        for unsafe_summary in ["입력된 1건의 근거를 정리했습니다.", "대출 승인이 보장됩니다."]:
            with self.subTest(unsafe_summary):
                def handler(request: httpx.Request) -> httpx.Response:
                    content = json.dumps(
                        {"summary": unsafe_summary, "explanations": {}},
                        ensure_ascii=False,
                    )
                    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

                result = await LlmExplainer(configured, httpx.MockTransport(handler)).explain(
                    data,
                    score_evidence(data),
                    [],
                )
                self.assertFalse(result.llm_succeeded)
                self.assertNotEqual(result.summary, unsafe_summary)

    async def test_vietnamese_fallback_summary_is_localized(self) -> None:
        data = ApplicantInput(
            language="vi",
            nationality="Việt Nam",
            visa_type="E-9",
            employment_months=14,
            monthly_income_krw=2_700_000,
            telecom_paid_months=12,
            insurance_paid_months=8,
            remittance_monthly_amount=600_000,
            remittance_currency="VND",
            remittance_months=6,
        )

        result = await LlmExplainer(settings()).explain(data, score_evidence(data), [])

        self.assertFalse(result.llm_succeeded)
        self.assertIn("Mức độ đầy đủ", result.summary)
        self.assertIn("Tự khai", result.items[0].source)

    async def test_vision_values_outside_applicant_constraints_need_review(self) -> None:
        image_buffer = BytesIO()
        Image.new("RGB", (4, 4), "white").save(image_buffer, format="PNG")

        def handler(request: httpx.Request) -> httpx.Response:
            content = json.dumps(
                {
                    "remittance_monthly_amount": -1,
                    "remittance_currency": "12$",
                    "remittance_months": 601,
                }
            )
            return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

        configured = settings(llm_api_key="test", llm_model="test-model", llm_api_base_url="https://llm.example/v1")
        result = await LlmExplainer(configured, httpx.MockTransport(handler)).extract_document(
            EvidenceCategory.REMITTANCE,
            image_buffer.getvalue(),
            "image/png",
        )

        self.assertEqual(result.status, "needs_review")
        self.assertEqual(result.fields, {})
        self.assertTrue(result.warnings)

    async def test_vision_normalizes_common_numeric_format(self) -> None:
        image_buffer = BytesIO()
        Image.new("RGB", (4, 4), "white").save(image_buffer, format="PNG")

        def handler(request: httpx.Request) -> httpx.Response:
            content = json.dumps({"employment_months": " 14 ", "monthly_income_krw": "2,500,000"})
            return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

        configured = settings(llm_api_key="test", llm_model="test-model", llm_api_base_url="https://llm.example/v1")
        result = await LlmExplainer(configured, httpx.MockTransport(handler)).extract_document(
            EvidenceCategory.EMPLOYMENT,
            image_buffer.getvalue(),
            "image/png",
        )

        self.assertEqual(result.status, "extracted")
        self.assertEqual(result.fields["employment_months"], 14)
        self.assertEqual(result.fields["monthly_income_krw"], 2_500_000)

    def test_document_render_resource_limits(self) -> None:
        image_buffer = BytesIO()
        Image.new("RGB", (2, 2), "white").save(image_buffer, format="PNG")
        with patch("app.services.llm_explainer.MAX_IMAGE_PIXELS", 3):
            with self.assertRaises(ValueError):
                _document_images(image_buffer.getvalue(), "image/png")

        document = pymupdf.open()
        document.new_page()
        pdf_bytes = document.tobytes()
        document.close()
        with patch("app.services.llm_explainer.MAX_PDF_PAGES", 0):
            with self.assertRaises(ValueError):
                _document_images(pdf_bytes, "application/pdf")
        with patch("app.services.llm_explainer.MAX_PDF_RENDERED_PIXELS", 1):
            with self.assertRaises(ValueError):
                _document_images(pdf_bytes, "application/pdf")


if __name__ == "__main__":
    unittest.main()
