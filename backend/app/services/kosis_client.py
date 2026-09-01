from datetime import datetime, timezone
import time

import httpx

from app.core.config import Settings
from app.models.schemas import DataSourceStatus, ExternalMetric


KOSIS_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"


class KosisClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self.transport = transport
        self._cached: ExternalMetric | None = None
        self._expires_at = 0.0

    async def get_population_context(self) -> ExternalMetric:
        if self._cached and time.monotonic() < self._expires_at:
            return self._cached.model_copy(update={"status": DataSourceStatus.CACHE})
        if not self.settings.kosis_api_key:
            return self._fallback("API 키가 없어 배경지표를 분석에 반영하지 않았습니다.")

        params = {
            "method": "getList",
            "apiKey": self.settings.kosis_api_key,
            "orgId": "101",
            "tblId": "DT_1IN1502",
            "objL1": "00",
            "itmId": "T100",
            "prdSe": "Y",
            "newEstPrdCnt": "1",
            "format": "json",
            "jsonVD": "Y",
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.request_timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.get(KOSIS_URL, params=params)
                response.raise_for_status()
                payload = response.json()
            if isinstance(payload, dict) and payload.get("err"):
                raise ValueError(f"KOSIS error {payload['err']}")
            if not isinstance(payload, list) or not payload:
                raise ValueError("KOSIS returned no rows")

            row = payload[0]
            raw_value = str(row.get("DT", "")).replace(",", "").strip()
            value: float | str = float(raw_value) if raw_value.replace(".", "", 1).isdigit() else raw_value
            metric = ExternalMetric(
                name=str(row.get("TBL_NM") or "KOSIS 국내 인구 배경지표"),
                value=value,
                unit=str(row.get("UNIT_NM") or "명"),
                status=DataSourceStatus.LIVE,
                source_name="국가통계포털 KOSIS",
                checked_at=_now(),
                note=f"{row.get('PRD_DE', '')}년 자료이며 개인별 근거 산정에는 사용하지 않습니다.",
            )
            self._cached = metric
            self._expires_at = time.monotonic() + self.settings.external_cache_ttl_seconds
            return metric
        except (httpx.HTTPError, ValueError, TypeError):
            if self._cached:
                return self._cached.model_copy(
                    update={"status": DataSourceStatus.CACHE, "note": "실시간 조회 실패로 마지막 정상 자료를 사용했습니다."}
                )
            return self._fallback("실시간 조회에 실패해 배경지표를 분석에 반영하지 않았습니다.")

    @staticmethod
    def _fallback(note: str) -> ExternalMetric:
        return ExternalMetric(
            name="KOSIS 국내 인구 배경지표",
            status=DataSourceStatus.FALLBACK,
            source_name="국가통계포털 KOSIS",
            checked_at=_now(),
            note=note,
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

