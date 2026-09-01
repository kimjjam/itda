from datetime import datetime, timedelta, timezone
import re
import time

import httpx

from app.core.config import Settings
from app.models.schemas import DataSourceStatus, ExternalMetric


EXIM_URL = "https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON"


class ExchangeRateClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self.transport = transport
        self._cache: dict[str, tuple[float, ExternalMetric]] = {}

    async def get_rate(self, currency: str) -> ExternalMetric:
        currency = currency.upper()
        if currency == "KRW":
            return ExternalMetric(
                name="원화 기준 환율",
                value=1.0,
                unit="KRW/KRW",
                status=DataSourceStatus.LIVE,
                source_name="원화 입력",
                checked_at=_now(),
            )

        cached = self._cache.get(currency)
        if cached and time.monotonic() < cached[0]:
            return cached[1].model_copy(update={"status": DataSourceStatus.CACHE})
        if not self.settings.exim_exchange_api_key:
            return self._fallback(currency, "API 키가 없어 원화 환산을 생략했습니다.")

        try:
            today = datetime.now(timezone(timedelta(hours=9))).date()
            async with httpx.AsyncClient(
                timeout=self.settings.request_timeout_seconds,
                transport=self.transport,
            ) as client:
                for offset in range(7):
                    search_date = (today - timedelta(days=offset)).strftime("%Y%m%d")
                    response = await client.get(
                        EXIM_URL,
                        params={
                            "authkey": self.settings.exim_exchange_api_key,
                            "searchdate": search_date,
                            "data": "AP01",
                        },
                    )
                    response.raise_for_status()
                    payload = response.json()
                    row = _find_currency(payload, currency)
                    if row:
                        metric = ExternalMetric(
                            name=f"{currency} 원화 환산 기준",
                            value=_one_unit_rate(row),
                            unit=f"KRW/{currency}",
                            status=DataSourceStatus.LIVE,
                            source_name="한국수출입은행 환율 Open API",
                            checked_at=_now(),
                            note=f"{search_date} 매매기준율입니다.",
                        )
                        self._cache[currency] = (
                            time.monotonic() + self.settings.external_cache_ttl_seconds,
                            metric,
                        )
                        return metric
            raise ValueError("exchange rate not found")
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            if cached:
                return cached[1].model_copy(
                    update={"status": DataSourceStatus.CACHE, "note": "실시간 조회 실패로 마지막 정상 환율을 사용했습니다."}
                )
            return self._fallback(currency, "실시간 조회에 실패해 원화 환산을 생략했습니다.")

    @staticmethod
    def _fallback(currency: str, note: str) -> ExternalMetric:
        return ExternalMetric(
            name=f"{currency} 원화 환산 기준",
            status=DataSourceStatus.FALLBACK,
            source_name="한국수출입은행 환율 Open API",
            checked_at=_now(),
            note=note,
        )


def _find_currency(payload: object, currency: str) -> dict[str, object] | None:
    if not isinstance(payload, list):
        raise ValueError("invalid exchange response")
    for row in payload:
        if not isinstance(row, dict):
            continue
        result = int(row.get("result") or 0)
        if result in {2, 3, 4}:
            raise ValueError(f"exchange API error {result}")
        if result != 1:
            continue
        if str(row.get("cur_unit") or "").split("(", 1)[0] == currency:
            return row
    return None


def _one_unit_rate(row: dict[str, object]) -> float:
    unit = str(row["cur_unit"])
    rate = float(str(row["deal_bas_r"]).replace(",", ""))
    factor_match = re.search(r"\((\d+)\)", unit)
    return rate / int(factor_match.group(1)) if factor_match else rate


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
