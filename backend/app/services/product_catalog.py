import logging

from app.models.schemas import Product, VisaType
from app.services.persistence_client import PersistenceClient, PersistenceReadError


VERIFIED_AT = "2026-08-31"
logger = logging.getLogger(__name__)

FALLBACK_CATALOG = [
    Product(
        name="Hi-OK론",
        provider="OK저축은행",
        category="저축은행_신용대출",
        eligible_visas=["E-9", "E-7", "F-2", "F-6", "D-2"],
        limit_text="100만원~6,000만원",
        rate_text="연 14.23%~19.99% (2026-05-01 기준)",
        requirement_text="소득증빙 가능, NICE 300점 이상, 내부 심사기준 적용",
        source_url="https://m.oksavingsbank.com/product/lon/frgn.jsp?addUrl=%2F%23%2FgdsLonCrdaDtl&lonGdsSqno=172&menuCd=00170",
        verified_at=VERIFIED_AT,
        match_reason="",
    ),
    Product(
        name="웰컴외국인대출",
        provider="웰컴저축은행",
        category="저축은행_신용대출",
        eligible_visas=["E-9", "E-7", "D-2"],
        limit_text="최대 3,000만원",
        rate_text="연 7.61%~19.90% (2026-07-15 기준)",
        requirement_text="체류기간 만료까지 1개월 이상, NICE 300점 이상, 소득·심사 결과별 차등",
        source_url="https://m.welcomebank.co.kr/ib20/mnu/MWBDSP000000?prdCd=1275101184&sysDsCd=02",
        verified_at=VERIFIED_AT,
        match_reason="",
    ),
    Product(
        name="Oh! YES loan",
        provider="예가람저축은행",
        category="저축은행_신용대출",
        eligible_visas=["E-9", "E-7", "F-2", "F-6"],
        limit_text="최대 4,000만원",
        rate_text="연 11.5%~19.9%",
        requirement_text="대한민국 체류 및 소득증빙 가능한 외국인 근로자, 내부 심사기준 적용",
        source_url="https://nsl.yegaramsb.co.kr/lon/inq/loanList.frm",
        verified_at=VERIFIED_AT,
        match_reason="",
    ),
    Product(
        name="KB WELCOME PLUS 전세자금대출",
        provider="KB국민은행",
        category="시중은행_전세대출",
        eligible_visas=["D-2", "E-7", "F-2", "F-6"],
        limit_text="최대 2억원 (보증·임차보증금 조건 적용)",
        rate_text="연 4.23%~5.74% (2026-08-27 공시 범위)",
        requirement_text="국내소득 3개월 이상, SGI 보증 가능, 비자 잔여기간 등 세부요건 적용",
        source_url="https://obank.kbstar.com/quics?QSL=F&cc=b104363%3Ab104516&isNew=N&page=C103507&prcode=LN20001120",
        verified_at=VERIFIED_AT,
        match_reason="",
    ),
    Product(
        name="SOL글로벌 전세대출(서울보증_외국인)",
        provider="신한은행",
        category="시중은행_전세대출",
        eligible_visas=[],
        requirement_text="현행 공식 문서에서 상품명만 확인됨. 세부 조건은 금융기관 확인 필요",
        source_url="https://img.shinhan.com/sbank2016/seol/20170630814200000030LC000030.PDF",
        verified_at=VERIFIED_AT,
        match_reason="",
    ),
    Product(
        name="TOGETHER외국인신용대출",
        provider="광주은행",
        category="시중은행_외국인신용대출",
        eligible_visas=[],
        limit_text="100만~5,000만원 (2025-03-31 공시)",
        requirement_text="국내 장기체류 등록외국인·거소신고 동포 중 요건을 충족한 급여소득자",
        source_url="https://www.kjbank.com/ib20/mnu/FPMLOAN020001",
        verified_at=VERIFIED_AT,
        match_reason="",
    ),
    Product(
        name="JB Bravo KOREA 대출",
        provider="전북은행",
        category="시중은행_외국인신용대출",
        eligible_visas=[],
        requirement_text="체류자격별 세부 대상·한도·금리는 금융기관 확인 필요",
        source_url="https://www.jbbank.co.kr/loan_gdnc_cdln.act",
        verified_at=VERIFIED_AT,
        match_reason="",
    ),
    Product(
        name="BNK웰컴 글로벌대출",
        provider="부산은행",
        category="시중은행_외국인신용대출",
        eligible_visas=[],
        requirement_text="외국인 근로자 대상. 체류자격·한도·금리는 금융기관 확인 필요",
        source_url="https://www.busanbank.co.kr/ib20/mnu/FPMLON092001001",
        verified_at=VERIFIED_AT,
        match_reason="",
    ),
    Product(
        name="하나 외국인 EZ Loan",
        provider="하나은행",
        category="시중은행_외국인신용대출",
        eligible_visas=["E-7", "E-9"],
        limit_text="100만~1,000만원",
        requirement_text="외국인등록증 보유, 국내 거주·현 직장 급여소득 각 3개월 이상, 거래외국환 지정. E-9는 최초 입국자",
        source_url="https://www.kebhana.com/cont/mall/mall08/mall0802/mall080204/1510586_115200.jsp?_menuNo=98786",
        verified_at="2026-09-01",
        match_reason="",
    ),
    Product(
        name="K dream 외국인신용대출",
        provider="BNK경남은행",
        category="시중은행_외국인신용대출",
        eligible_visas=[],
        requirement_text="국내 거주 외국인 근로자 전용. 세부 체류자격·한도·금리는 금융기관 확인 필요",
        source_url="https://www.bnkfg.com/download?seq=6565",
        verified_at="2026-09-01",
        match_reason="",
    ),
]


def match_products(
    visa_type: VisaType,
    language: str = "ko",
    catalog: list[Product] | None = None,
) -> list[Product]:
    products: list[Product] = []
    for product in FALLBACK_CATALOG if catalog is None else catalog:
        if visa_type in product.eligible_visas:
            reason = (
                f"Thị thực {visa_type} nằm trong danh sách đối tượng công khai; tổ chức tài chính vẫn quyết định cuối cùng."
                if language == "vi"
                else f"입력한 {visa_type} 체류자격이 공식 안내 대상에 포함됩니다. 최종 조건은 별도 심사가 필요합니다."
            )
        elif product.eligible_visas:
            continue
        else:
            reason = (
                "Thông tin công khai về loại thị thực còn hạn chế; hãy xác nhận điều kiện với tổ chức tài chính."
                if language == "vi"
                else "공개된 세부 체류자격 조건이 제한적이므로 금융기관 확인이 필요합니다."
            )
        products.append(product.model_copy(update={"match_reason": reason}))
    return products


async def load_matched_products(
    persistence: PersistenceClient,
    visa_type: VisaType,
    language: str = "ko",
) -> list[Product]:
    if not persistence.settings.database_configured:
        return match_products(visa_type, language)
    try:
        catalog = await persistence.get_active_products()
    except PersistenceReadError:
        logger.warning("Product catalog lookup failed; using static fallback")
        return match_products(visa_type, language)
    return match_products(visa_type, language, catalog)
