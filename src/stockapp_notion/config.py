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

    # --- 웹 UI (호스트/포트/로그인) ---

    @property
    def web_host(self) -> str:
        """기본값은 로컬 전용(127.0.0.1). Docker에서 외부 접속을 받으려면
        .env에서 0.0.0.0으로 바꾼다(실제 노출 범위는 포트 매핑/Tailscale이 결정)."""
        return os.getenv("WEB_HOST", "127.0.0.1")

    @property
    def web_port(self) -> int:
        return int(os.getenv("WEB_PORT", "5000"))

    @property
    def web_auth_enabled(self) -> bool:
        """WEB_USERNAME/WEB_PASSWORD가 설정되어 있으면 로그인을 요구한다.
        둘 다 비어 있으면(로컬 전용 사용 등) 인증 없이 기존처럼 동작한다."""
        return bool(os.getenv("WEB_USERNAME") and os.getenv("WEB_PASSWORD"))

    @property
    def web_username(self) -> str:
        return _require("WEB_USERNAME")

    @property
    def web_password(self) -> str:
        return _require("WEB_PASSWORD")

    # --- KIS(한국투자증권) Open API (선택 기능: KIS_APP_KEY 미설정 시 관련 기능 비활성) ---

    @property
    def kis_enabled(self) -> bool:
        return bool(os.getenv("KIS_APP_KEY"))

    @property
    def kis_app_key(self) -> str:
        return _require("KIS_APP_KEY")

    @property
    def kis_app_secret(self) -> str:
        return _require("KIS_APP_SECRET")

    @property
    def kis_account_no(self) -> str:
        """계좌번호 10자리(종합계좌 8자리 + 상품코드 2자리). 하이픈 없이 저장."""
        return _require("KIS_ACCOUNT_NO").replace("-", "")

    @property
    def kis_is_paper(self) -> bool:
        """기본값 모의투자(true). 실계좌 전환은 .env에서 명시적으로 false로 바꿔야 한다."""
        return os.getenv("KIS_IS_PAPER", "true").lower() == "true"

    @property
    def kis_base_url(self) -> str:
        if self.kis_is_paper:
            return "https://openapivts.koreainvestment.com:29443"
        return "https://openapi.koreainvestment.com:9443"


settings = Settings()
