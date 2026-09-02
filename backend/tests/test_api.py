import json
from io import BytesIO
from pathlib import Path
import unittest

from fastapi.testclient import TestClient
import pymupdf
from PIL import Image

from app.main import app


DEMO_SAMPLE_DIR = Path(__file__).resolve().parents[2] / "frontend" / "public" / "samples"


SAMPLE = {
    "nationality": "베트남",
    "visa_type": "E-9",
    "employment_months": 14,
    "monthly_income_krw": 2_700_000,
    "telecom_paid_months": 12,
    "insurance_paid_months": 8,
    "remittance_monthly_amount": 600_000,
    "remittance_currency": "VND",
    "remittance_months": 6,
    "document_categories": ["employment", "telecom"],
    "self_reported_risk": True,
}


class ApiTest(unittest.TestCase):
    client = TestClient(app)

    def test_health_and_ingest_without_credentials(self) -> None:
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        response = self.client.post("/api/ingest", json=SAMPLE)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["persistence_status"], "skipped")

    def test_analysis_stream_ignores_unpersisted_document_claims(self) -> None:
        response = self.client.post("/api/analyze/stream", json=SAMPLE)
        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.text.splitlines()]

        self.assertEqual(events[0]["step"], "kosis")
        self.assertEqual(events[-1]["step"], "complete")
        self.assertEqual(events[-1]["data"]["evidence_strength"], 22)
        self.assertTrue(events[-1]["data"]["risk_alert"]["active"])
        endpoint_products = self.client.get("/api/products", params={"visa_type": "E-9"}).json()
        self.assertEqual(
            {
                (product["provider"], product["name"], product["category"])
                for product in events[-1]["data"]["matched_products"]
            },
            {
                (product["provider"], product["name"], product["category"])
                for product in endpoint_products
            },
        )

    def test_product_catalog_uses_current_fallback_categories(self) -> None:
        products = self.client.get("/api/products", params={"visa_type": "E-9"}).json()
        names = {product["name"] for product in products}

        self.assertIn("하나 외국인 EZ Loan", names)
        self.assertIn("K dream 외국인신용대출", names)
        self.assertNotIn("KB WELCOME PLUS 전세자금대출", names)
        self.assertEqual(
            {product["category"] for product in products},
            {"저축은행_신용대출", "시중은행_전세대출", "시중은행_외국인신용대출"},
        )

    def test_image_and_pdf_uploads_are_validated_before_vision(self) -> None:
        image_buffer = BytesIO()
        Image.new("RGB", (40, 40), "white").save(image_buffer, format="PNG")
        pdf = pymupdf.open()
        pdf.new_page().insert_text((72, 72), "Employment evidence")

        samples = [
            ("evidence.png", "image/png", image_buffer.getvalue()),
            ("evidence.pdf", "application/pdf", pdf.tobytes()),
        ]
        for filename, content_type, content in samples:
            with self.subTest(filename=filename):
                response = self.client.post(
                    "/api/documents",
                    data={"session_id": "8be146ac-8275-4ec9-a6c9-bb38ed97eb1e", "category": "employment"},
                    files={"file": (filename, content, content_type)},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["status"], "needs_review")

    def test_bundled_demo_pdfs_use_the_document_pipeline(self) -> None:
        categories = {
            "employment-demo.pdf": "employment",
            "telecom-demo.pdf": "telecom",
            "insurance-demo.pdf": "insurance",
            "remittance-demo.pdf": "remittance",
        }
        for filename, category in categories.items():
            with self.subTest(filename=filename):
                content = (DEMO_SAMPLE_DIR / filename).read_bytes()
                response = self.client.post(
                    "/api/documents",
                    data={"session_id": "8be146ac-8275-4ec9-a6c9-bb38ed97eb1e", "category": category},
                    files={"file": (filename, content, "application/pdf")},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["status"], "needs_review")


if __name__ == "__main__":
    unittest.main()
