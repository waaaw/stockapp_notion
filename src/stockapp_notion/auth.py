"""웹 UI용 간단한 세션 기반 로그인.

`.env`에 WEB_USERNAME/WEB_PASSWORD가 둘 다 설정된 경우에만 로그인을 요구한다.
설정되어 있지 않으면(로컬 전용 사용 등) 기존처럼 인증 없이 동작한다 — 이미 로컬에서
쓰고 있는 사용자의 워크플로를 깨지 않기 위함이다.

비밀번호는 평문으로 .env에 저장하고 secrets.compare_digest로 비교한다(타이밍 공격 방지).
외부에 노출할 때는 이 로그인만으로 충분하다고 보지 않으며, Tailscale 등 사설망 경유를
함께 쓰는 것을 전제로 한다(README/배포 가이드 참고).
"""

import secrets

from flask import session

from stockapp_notion.config import settings

_SESSION_KEY = "authenticated"


def is_authenticated() -> bool:
    return session.get(_SESSION_KEY, False)


def mark_authenticated() -> None:
    session[_SESSION_KEY] = True


def check_credentials(username: str, password: str) -> bool:
    return secrets.compare_digest(username, settings.web_username) and secrets.compare_digest(
        password, settings.web_password
    )
