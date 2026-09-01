from dataclasses import dataclass

from app.models.schemas import ApplicantInput, EvidenceCategory, EvidenceItem, Language


@dataclass(frozen=True)
class ScoringResult:
    strength: int
    level: str
    items: list[EvidenceItem]


def _months_item(
    *,
    key: str,
    title: str,
    months: int,
    weights: tuple[int, int, int],
    verified: bool,
    verified_source: str,
    language: Language,
) -> tuple[int, EvidenceItem]:
    if months <= 0:
        points, strength = 0, "limited"
        explanation = (
            "Chưa có thời gian được khai báo; hồ sơ bổ sung sẽ giúp củng cố căn cứ."
            if language == "vi"
            else "입력된 기록 기간이 없어 관련 증빙을 추가하면 근거가 보강됩니다."
        )
    elif not verified:
        points, strength = weights[2], "limited"
        explanation = (
            "Đây chỉ là thông tin tự khai và chưa có hồ sơ tương ứng, nên chưa được xem là căn cứ đã xác minh."
            if language == "vi"
            else "자가 입력값만 있고 해당 증빙이 제출되지 않아 확인된 기록으로 보지 않습니다."
        )
    elif months >= 12:
        points, strength = weights[0], "strong"
        explanation = (
            "Hồ sơ đã nộp cho phép đối chiếu quá trình kéo dài từ mười hai tháng trở lên."
            if language == "vi"
            else "제출된 증빙에서 12개월 이상 이어진 기록을 검토할 수 있어 지속성을 뒷받침합니다."
        )
    elif months >= 6:
        points, strength = weights[1], "moderate"
        explanation = (
            "Hồ sơ đã nộp cho phép đối chiếu quá trình kéo dài từ sáu tháng trở lên."
            if language == "vi"
            else "제출된 증빙에서 6개월 이상 기록을 검토할 수 있어 일정한 지속성을 뒷받침합니다."
        )
    else:
        points, strength = weights[2], "limited"
        explanation = (
            "Thời gian trong hồ sơ còn ngắn; tài liệu bổ sung sẽ giúp củng cố căn cứ."
            if language == "vi"
            else "제출된 증빙의 기록 기간이 짧아 추가 자료가 있으면 근거가 보강됩니다."
        )

    source = verified_source if verified else ("Tự khai (chưa nộp hồ sơ)" if language == "vi" else "자가 입력(증빙 미제출)")
    value = f"{months} tháng" if language == "vi" else f"{months}개월"
    return points, EvidenceItem(
        key=key,
        title=title,
        value=value,
        strength=strength,
        explanation=explanation,
        source=source,
    )


def score_evidence(data: ApplicantInput) -> ScoringResult:
    documents = set(data.document_categories)
    is_vi = data.language == "vi"
    titles = (
        {
            "employment": "Tính liên tục của việc làm",
            "telecom": "Tính liên tục của thanh toán viễn thông",
            "insurance": "Tính liên tục của bảo hiểm y tế",
            "remittance": "Tính liên tục của chuyển tiền quốc tế",
            "income": "Căn cứ thu nhập",
        }
        if is_vi
        else {
            "employment": "재직 지속성",
            "telecom": "통신비 납부 지속성",
            "insurance": "건강보험료 납부 지속성",
            "remittance": "해외송금 패턴 지속성",
            "income": "소득 근거",
        }
    )
    sources = (
        {
            EvidenceCategory.EMPLOYMENT: "Thông tin tự khai và hồ sơ việc làm đã nộp",
            EvidenceCategory.TELECOM: "Thông tin tự khai và hồ sơ viễn thông đã nộp",
            EvidenceCategory.INSURANCE: "Thông tin tự khai và hồ sơ bảo hiểm đã nộp",
            EvidenceCategory.REMITTANCE: "Thông tin tự khai và hồ sơ chuyển tiền đã nộp",
        }
        if is_vi
        else {
            EvidenceCategory.EMPLOYMENT: "재직정보 입력 및 제출 증빙",
            EvidenceCategory.TELECOM: "통신비 납부 입력 및 제출 증빙",
            EvidenceCategory.INSURANCE: "건강보험료 납부 입력 및 제출 증빙",
            EvidenceCategory.REMITTANCE: "해외송금 입력 및 제출 증빙",
        }
    )

    employment_verified = EvidenceCategory.EMPLOYMENT in documents
    employment_points, employment = _months_item(
        key="employment",
        title=titles["employment"],
        months=data.employment_months,
        weights=(30, 20, 8),
        verified=employment_verified,
        verified_source=sources[EvidenceCategory.EMPLOYMENT],
        language=data.language,
    )
    telecom_points, telecom = _months_item(
        key="telecom",
        title=titles["telecom"],
        months=data.telecom_paid_months,
        weights=(20, 12, 4),
        verified=EvidenceCategory.TELECOM in documents,
        verified_source=sources[EvidenceCategory.TELECOM],
        language=data.language,
    )
    insurance_points, insurance = _months_item(
        key="insurance",
        title=titles["insurance"],
        months=data.insurance_paid_months,
        weights=(20, 12, 4),
        verified=EvidenceCategory.INSURANCE in documents,
        verified_source=sources[EvidenceCategory.INSURANCE],
        language=data.language,
    )
    remittance_points, remittance = _months_item(
        key="remittance",
        title=titles["remittance"],
        months=data.remittance_months,
        weights=(15, 9, 3),
        verified=EvidenceCategory.REMITTANCE in documents,
        verified_source=sources[EvidenceCategory.REMITTANCE],
        language=data.language,
    )

    if data.monthly_income_krw <= 0:
        income_points, income_strength = 0, "limited"
        income_explanation = (
            "Chưa có thông tin thu nhập; hồ sơ việc làm hoặc bảng lương sẽ giúp củng cố căn cứ."
            if is_vi
            else "소득 정보가 없어 재직·급여 증빙을 추가하면 근거가 보강됩니다."
        )
    elif employment_verified:
        income_points, income_strength = 15, "strong"
        income_explanation = (
            "Hồ sơ việc làm đã nộp cho phép đối chiếu thông tin thu nhập tự khai."
            if is_vi
            else "제출된 재직 증빙과 함께 입력 소득 정보를 검토할 수 있습니다."
        )
    else:
        income_points, income_strength = 3, "limited"
        income_explanation = (
            "Thu nhập chỉ là thông tin tự khai và chưa có hồ sơ tương ứng, nên chưa được xem là căn cứ đã xác minh."
            if is_vi
            else "소득은 자가 입력값만 있고 재직·급여 증빙이 제출되지 않아 확인된 근거로 보지 않습니다."
        )
    income = EvidenceItem(
        key="income",
        title=titles["income"],
        value=f"{data.monthly_income_krw:,} KRW/tháng" if is_vi else f"월 {data.monthly_income_krw:,}원",
        strength=income_strength,
        explanation=income_explanation,
        source=sources[EvidenceCategory.EMPLOYMENT] if employment_verified else ("Tự khai (chưa nộp hồ sơ)" if is_vi else "자가 입력(증빙 미제출)"),
    )

    strength = min(100, employment_points + telecom_points + insurance_points + remittance_points + income_points)
    level = "충분" if strength >= 75 else "보통" if strength >= 45 else "추가 자료 필요"
    return ScoringResult(strength=strength, level=level, items=[employment, telecom, insurance, income, remittance])
