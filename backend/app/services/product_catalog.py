import logging

from app.models.schemas import Product, VisaType
from app.services.persistence_client import PersistenceClient, PersistenceReadError


VERIFIED_AT = "2026-08-31"
logger = logging.getLogger(__name__)

VI_PRODUCT_COPY: dict[tuple[str, str], dict[str, str]] = {
    ("OK저축은행", "Hi-OK론"): {
        "provider": "OK Savings Bank",
        "name": "Hi-OK Loan",
        "limit_text": "1–60 triệu KRW",
        "rate_text": "14,23%–19,99%/năm (tính đến 2026-05-01)",
        "requirement_text": "Có thể chứng minh thu nhập, điểm NICE từ 300 và áp dụng tiêu chí thẩm định nội bộ.",
    },
    ("웰컴저축은행", "웰컴외국인대출"): {
        "provider": "Welcome Savings Bank",
        "name": "Khoản vay Welcome dành cho người nước ngoài",
        "limit_text": "Tối đa 30 triệu KRW",
        "rate_text": "7,61%–19,90%/năm (tính đến 2026-07-15)",
        "requirement_text": "Thời hạn cư trú còn ít nhất một tháng, điểm NICE từ 300; điều kiện khác nhau theo thu nhập và kết quả thẩm định.",
    },
    ("예가람저축은행", "Oh! YES loan"): {
        "provider": "Yegaram Savings Bank",
        "name": "Oh! YES loan",
        "limit_text": "Tối đa 40 triệu KRW",
        "rate_text": "11,5%–19,9%/năm",
        "requirement_text": "Người lao động nước ngoài cư trú tại Hàn Quốc, có thể chứng minh thu nhập; áp dụng tiêu chí thẩm định nội bộ.",
    },
    ("KB국민은행", "KB WELCOME PLUS 전세자금대출"): {
        "provider": "KB Kookmin Bank",
        "name": "Khoản vay tiền đặt cọc thuê nhà KB WELCOME PLUS",
        "limit_text": "Tối đa 200 triệu KRW (áp dụng điều kiện bảo lãnh và tiền đặt cọc thuê nhà)",
        "rate_text": "4,23%–5,74%/năm (phạm vi công bố ngày 2026-08-27)",
        "requirement_text": "Có thu nhập trong nước từ ba tháng, đủ điều kiện bảo lãnh SGI và đáp ứng yêu cầu chi tiết như thời hạn visa còn lại.",
    },
    ("신한은행", "SOL글로벌 전세대출(서울보증_외국인)"): {
        "provider": "Shinhan Bank",
        "name": "Khoản vay tiền đặt cọc thuê nhà SOL Global (SGI · người nước ngoài)",
        "requirement_text": "Tài liệu chính thức hiện hành chỉ xác nhận tên sản phẩm; vui lòng hỏi tổ chức tài chính về điều kiện chi tiết.",
    },
    ("광주은행", "TOGETHER외국인신용대출"): {
        "provider": "Kwangju Bank",
        "name": "Khoản vay tín chấp TOGETHER dành cho người nước ngoài",
        "limit_text": "1–50 triệu KRW (công bố ngày 2025-03-31)",
        "requirement_text": "Người lao động hưởng lương đáp ứng điều kiện, thuộc nhóm người nước ngoài đăng ký cư trú dài hạn hoặc đồng bào đã khai báo cư trú.",
    },
    ("전북은행", "JB Bravo KOREA 대출"): {
        "provider": "Jeonbuk Bank",
        "name": "JB Bravo KOREA Loan",
        "requirement_text": "Vui lòng hỏi tổ chức tài chính về đối tượng, hạn mức và lãi suất chi tiết theo loại visa.",
    },
    ("부산은행", "BNK웰컴 글로벌대출"): {
        "provider": "BNK Busan Bank",
        "name": "BNK Welcome Global Loan",
        "requirement_text": "Dành cho người lao động nước ngoài; vui lòng hỏi tổ chức tài chính về loại visa, hạn mức và lãi suất.",
    },
    ("하나은행", "하나 외국인 EZ Loan"): {
        "provider": "Hana Bank",
        "name": "Hana EZ Loan dành cho người nước ngoài",
        "limit_text": "1–10 triệu KRW",
        "requirement_text": "Có thẻ đăng ký người nước ngoài; cư trú tại Hàn Quốc và có thu nhập lương tại nơi làm việc hiện tại, mỗi điều kiện từ ba tháng; chỉ định ngân hàng giao dịch ngoại hối. Visa E-9 chỉ áp dụng cho người nhập cảnh lần đầu.",
    },
    ("BNK경남은행", "K dream 외국인신용대출"): {
        "provider": "BNK Kyongnam Bank",
        "name": "Khoản vay tín chấp K dream dành cho người nước ngoài",
        "requirement_text": "Dành riêng cho người lao động nước ngoài cư trú tại Hàn Quốc; vui lòng hỏi tổ chức tài chính về loại visa, hạn mức và lãi suất chi tiết.",
    },
}

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
        display_copy = VI_PRODUCT_COPY.get((product.provider, product.name), {}) if language == "vi" else {}
        products.append(product.model_copy(update={**display_copy, "match_reason": reason}))
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
