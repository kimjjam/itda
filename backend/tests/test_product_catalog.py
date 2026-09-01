from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from app.models.schemas import Product
from app.services.persistence_client import PersistenceReadError
from app.services.product_catalog import load_matched_products, match_products


class ProductCatalogTest(unittest.IsolatedAsyncioTestCase):
    def test_excludes_known_visa_mismatches_but_keeps_unknown_eligibility(self) -> None:
        products = match_products("E-9")
        names = {item.name for item in products}

        self.assertNotIn("KB WELCOME PLUS 전세자금대출", names)
        self.assertIn("하나 외국인 EZ Loan", names)
        self.assertIn("K dream 외국인신용대출", names)
        self.assertEqual(
            {item.category for item in products},
            {"저축은행_신용대출", "시중은행_전세대출", "시중은행_외국인신용대출"},
        )

    def test_localizes_match_reason(self) -> None:
        reason = match_products("E-9", "vi")[0].match_reason
        self.assertIn("Thị thực E-9", reason)

    async def test_prefers_database_catalog_and_applies_common_matching(self) -> None:
        database_product = Product(
            name="DB 상품",
            provider="테스트은행",
            category="시중은행_외국인신용대출",
            eligible_visas=["E-9"],
            match_reason="",
        )
        get_active_products = AsyncMock(return_value=[database_product])
        persistence = SimpleNamespace(
            settings=SimpleNamespace(database_configured=True),
            get_active_products=get_active_products,
        )

        products = await load_matched_products(persistence, "E-9", "vi")

        self.assertEqual([item.name for item in products], ["DB 상품"])
        self.assertIn("Thị thực E-9", products[0].match_reason)
        get_active_products.assert_awaited_once_with()

    async def test_uses_fallback_when_database_is_unconfigured_or_fails(self) -> None:
        unconfigured_read = AsyncMock()
        unconfigured = SimpleNamespace(
            settings=SimpleNamespace(database_configured=False),
            get_active_products=unconfigured_read,
        )
        failed = SimpleNamespace(
            settings=SimpleNamespace(database_configured=True),
            get_active_products=AsyncMock(side_effect=PersistenceReadError("unavailable")),
        )

        without_database = await load_matched_products(unconfigured, "E-9")
        after_failure = await load_matched_products(failed, "E-9")

        self.assertIn("하나 외국인 EZ Loan", {item.name for item in without_database})
        self.assertEqual(
            {item.name for item in without_database},
            {item.name for item in after_failure},
        )
        unconfigured_read.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
