"""Notion 워크스페이스에 4개의 데이터베이스(종목 마스터/매매내역/포트폴리오 요약/배당금 내역)를
생성하는 1회성 설치 스크립트.

사용법:
    python scripts/setup_notion_databases.py <parent_page_id>

parent_page_id는 DB들을 만들어 넣을 상위 Notion 페이지의 ID이며,
해당 페이지는 미리 Integration과 공유(Connect)되어 있어야 한다.

주의 1: 평가금액/평가손익/수익률 등은 Notion Formula/Rollup이 아니라
이 프로젝트의 Python 코드(portfolio.py)가 계산하여 Number 값으로 직접 기록한다.
따라서 이 스크립트는 Formula 속성을 만들지 않는다 (Notion API 제약이기도 하다).
실행 후 출력되는 database_id 4개를 .env 파일에 채워 넣으면 된다.

주의 2 (Notion API 2025-09 변경): 데이터베이스는 이제 하나 이상의 "data source"를
가지는 컨테이너이며, 속성 스키마는 database가 아닌 data source에 실린다.
데이터베이스 생성 시 속성은 `initial_data_source.properties`로 전달해야 하고,
relation 속성은 대상 database_id가 아닌 data_source_id를 참조해야 한다.
이 프로젝트의 나머지 코드(stocks.py 등)는 database_id로 조회 시 내부적으로
`notion_api.resolve_data_source_id`를 통해 data_source_id를 알아내 조회(query)한다.
"""

import sys

from stockapp_notion.notion_api import call_with_retry, get_client

SELECT = lambda options: {"select": {"options": [{"name": o} for o in options]}}  # noqa: E731


def _first_data_source_id(db: dict) -> str:
    return db["data_sources"][0]["id"]


def create_stocks_db(client, parent_page_id: str) -> tuple[str, str]:
    db = call_with_retry(
        client.databases.create,
        parent={"type": "page_id", "page_id": parent_page_id},
        title=[{"type": "text", "text": {"content": "종목 마스터"}}],
        initial_data_source={
            "properties": {
                "종목명": {"title": {}},
                "종목코드": {"rich_text": {}},
                "시장구분": SELECT(["코스피", "코스닥", "나스닥", "NYSE", "기타"]),
                "섹터": {"select": {"options": []}},
                "현재가": {"number": {"format": "number"}},
                "통화": SELECT(["KRW", "USD"]),
            }
        },
    )
    return db["id"], _first_data_source_id(db)


def create_transactions_db(client, parent_page_id: str, stocks_data_source_id: str) -> str:
    db = call_with_retry(
        client.databases.create,
        parent={"type": "page_id", "page_id": parent_page_id},
        title=[{"type": "text", "text": {"content": "매매 내역"}}],
        initial_data_source={
            "properties": {
                "거래일자": {"date": {}},
                "종목": {
                    "relation": {
                        "data_source_id": stocks_data_source_id,
                        "single_property": {},
                    }
                },
                "매매구분": SELECT(["매수", "매도"]),
                "수량": {"number": {"format": "number"}},
                "단가": {"number": {"format": "number"}},
                "수수료": {"number": {"format": "number"}},
                "총거래금액": {"number": {"format": "number"}},
            }
        },
    )
    return db["id"]


def create_portfolio_db(client, parent_page_id: str, stocks_data_source_id: str) -> str:
    db = call_with_retry(
        client.databases.create,
        parent={"type": "page_id", "page_id": parent_page_id},
        title=[{"type": "text", "text": {"content": "포트폴리오 요약"}}],
        initial_data_source={
            "properties": {
                "종목": {
                    "relation": {
                        "data_source_id": stocks_data_source_id,
                        "single_property": {},
                    }
                },
                "보유수량": {"number": {"format": "number"}},
                "평균단가": {"number": {"format": "number"}},
                "평가금액": {"number": {"format": "number"}},
                "평가손익": {"number": {"format": "number"}},
                "수익률(%)": {"number": {"format": "number"}},
            }
        },
    )
    return db["id"]


def create_dividends_db(client, parent_page_id: str, stocks_data_source_id: str) -> str:
    db = call_with_retry(
        client.databases.create,
        parent={"type": "page_id", "page_id": parent_page_id},
        title=[{"type": "text", "text": {"content": "배당금 내역"}}],
        initial_data_source={
            "properties": {
                "지급일": {"date": {}},
                "종목": {
                    "relation": {
                        "data_source_id": stocks_data_source_id,
                        "single_property": {},
                    }
                },
                "세전배당금": {"number": {"format": "number"}},
                "세후배당금": {"number": {"format": "number"}},
            }
        },
    )
    return db["id"]


def main() -> None:
    if len(sys.argv) != 2:
        print("사용법: python scripts/setup_notion_databases.py <parent_page_id>")
        sys.exit(1)

    parent_page_id = sys.argv[1]
    client = get_client()

    stocks_id, stocks_ds_id = create_stocks_db(client, parent_page_id)
    print(f"DB_STOCKS_ID={stocks_id}")

    transactions_id = create_transactions_db(client, parent_page_id, stocks_ds_id)
    print(f"DB_TRANSACTIONS_ID={transactions_id}")

    portfolio_id = create_portfolio_db(client, parent_page_id, stocks_ds_id)
    print(f"DB_PORTFOLIO_ID={portfolio_id}")

    dividends_id = create_dividends_db(client, parent_page_id, stocks_ds_id)
    print(f"DB_DIVIDENDS_ID={dividends_id}")

    print("\n위 4줄을 .env 파일에 복사해 넣으세요.")


if __name__ == "__main__":
    main()
