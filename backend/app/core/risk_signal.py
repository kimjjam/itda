from app.models.schemas import Language, RiskAlert


def detect_risk_signal(self_reported_risk: bool, language: Language = "ko") -> RiskAlert:
    if not self_reported_risk:
        return RiskAlert(active=False)
    if language == "vi":
        return RiskAlert(
            active=True,
            message="Bạn đã khai báo từng sử dụng tín dụng phi chính thức hoặc khoản vay lãi suất cao.",
            guidance=(
                "Trước khi vay thêm, hãy kiểm tra các kênh tư vấn tài chính công "
                "phù hợp với hoàn cảnh của bạn."
            ),
        )
    return RiskAlert(
        active=True,
        message="과거 불법사금융 또는 고금리 대출 이용 경험이 입력되었습니다.",
        guidance="추가 차입을 결정하기 전에 공공 금융상담 채널에서 현재 상황에 맞는 지원을 먼저 확인해 주세요.",
    )
