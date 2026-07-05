"""거래/배당/종목 입력값 검증. Notion에 쓰기 전에 잘못된 입력을 미리 걸러낸다."""

from datetime import datetime


def validate_positive(value: float, field_name: str) -> None:
    if value <= 0:
        raise ValueError(f"{field_name}은(는) 0보다 커야 합니다: {value}")


def validate_non_negative(value: float, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name}은(는) 0 이상이어야 합니다: {value}")


def validate_date_str(date_str: str, field_name: str = "거래일자") -> None:
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{field_name}은(는) YYYY-MM-DD 형식이어야 합니다: {date_str}") from exc


def validate_non_empty(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name}이(가) 비어 있습니다")
