import time

from notion_client import Client
from notion_client.errors import APIResponseError

from stockapp_notion.config import settings
from stockapp_notion.logging_config import get_logger

logger = get_logger(__name__)

_RETRYABLE_CODES = {"rate_limited", "internal_server_error", "service_unavailable"}
_MAX_RETRIES = 5
_BASE_DELAY_SECONDS = 1.0


def get_client() -> Client:
    return Client(auth=settings.notion_token)


_data_source_id_cache: dict[str, str] = {}


def resolve_data_source_id(client: Client, database_id: str) -> str:
    """Notion의 2025-09 API 변경으로 데이터베이스 조회(query)는 database_id가 아닌
    data_source_id를 요구한다. database_id -> 기본 data_source_id를 조회해 캐싱한다."""
    if database_id not in _data_source_id_cache:
        db = call_with_retry(client.databases.retrieve, database_id=database_id)
        _data_source_id_cache[database_id] = db["data_sources"][0]["id"]
    return _data_source_id_cache[database_id]


def call_with_retry(fn, *args, **kwargs):
    """Notion API 호출을 감싸 rate limit(초당 3회) 및 일시적 오류에 대해
    지수 백오프로 재시도한다."""
    last_error: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except APIResponseError as exc:
            last_error = exc
            code = getattr(exc, "code", "")
            if code not in _RETRYABLE_CODES or attempt == _MAX_RETRIES:
                logger.error("Notion API 호출 실패 (재시도 불가 또는 최대 재시도 초과): %s", exc)
                raise
            delay = _BASE_DELAY_SECONDS * (2 ** (attempt - 1))
            logger.warning(
                "Notion API 재시도 %s/%s (%s) - %.1f초 후 재시도",
                attempt,
                _MAX_RETRIES,
                code,
                delay,
            )
            time.sleep(delay)
    raise last_error  # pragma: no cover
