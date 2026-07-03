import os

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"환경변수 {name}이(가) 설정되지 않았습니다. .env 파일을 확인하세요.")
    return value


class Settings:
    """지연 평가된 설정값. 임포트 시점이 아닌 실제 사용 시점에 .env를 읽는다."""

    @property
    def notion_token(self) -> str:
        return _require("NOTION_TOKEN")

    @property
    def db_stocks_id(self) -> str:
        return _require("DB_STOCKS_ID")

    @property
    def db_transactions_id(self) -> str:
        return _require("DB_TRANSACTIONS_ID")

    @property
    def db_portfolio_id(self) -> str:
        return _require("DB_PORTFOLIO_ID")

    @property
    def db_dividends_id(self) -> str | None:
        return os.getenv("DB_DIVIDENDS_ID") or None

    @property
    def log_level(self) -> str:
        return os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
