"""Notion 페이지 dict에서 속성 값을 꺼내는 공용 헬퍼.
portfolio.py/webapp.py/prices.py에 중복되어 있던 로직을 한 곳으로 모았다."""


def prop_title(page: dict, name: str) -> str:
    items = page["properties"][name]["title"]
    return items[0]["text"]["content"] if items else ""


def prop_rich_text(page: dict, name: str) -> str:
    items = page["properties"][name]["rich_text"]
    return items[0]["text"]["content"] if items else ""


def prop_select_name(page: dict, name: str) -> str:
    select = page["properties"][name]["select"]
    return select["name"] if select else ""


def prop_number(page: dict, name: str) -> float:
    return page["properties"][name]["number"] or 0
