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


def ensure_property(client: Client, data_source_id: str, prop_name: str, prop_schema: dict) -> None:
    """data source 스키마에 prop_name이 없으면 추가한다(있으면 아무 것도 하지 않는 멱등 동작).
    Formula/Rollup은 API로 만들 수 없어 Number/Select 등 단순 타입에만 사용한다."""
    data_source = call_with_retry(client.data_sources.retrieve, data_source_id=data_source_id)
    if prop_name in data_source["properties"]:
        return
    call_with_retry(
        client.data_sources.update,
        data_source_id=data_source_id,
        properties={prop_name: prop_schema},
    )
    logger.info("data source %s에 속성 추가: %s", data_source_id, prop_name)


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
