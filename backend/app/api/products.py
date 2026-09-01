from typing import Literal

from fastapi import APIRouter, Query, Request

from app.models.schemas import Product, VisaType
from app.services.product_catalog import load_matched_products


router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[Product])
async def products(
    request: Request,
    visa_type: VisaType = Query(...),
    language: Literal["ko", "vi"] = Query("ko"),
) -> list[Product]:
    return await load_matched_products(request.app.state.persistence, visa_type, language)
