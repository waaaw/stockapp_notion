"""APScheduler를 이용한 스케줄러 실행 예시 (장 마감 후 매일 1회 갱신).
cron을 선호한다면 이 스크립트 대신 README의 crontab 예시를 사용해도 된다.

사용법:
    python scripts/run_daily_update.py
    (포그라운드에서 계속 실행되며 매일 지정 시각에 daily-update를 수행한다)
"""

from apscheduler.schedulers.blocking import BlockingScheduler

from stockapp_notion.cli import cmd_daily_update
from stockapp_notion.logging_config import get_logger

logger = get_logger(__name__)

# 한국 장 마감(15:30) 이후 여유를 두고 16:00에 실행
RUN_HOUR = 16
RUN_MINUTE = 0


def job() -> None:
    logger.info("일일 배치 시작")
    cmd_daily_update(None)
    logger.info("일일 배치 종료")


def main() -> None:
    scheduler = BlockingScheduler(timezone="Asia/Seoul")
    scheduler.add_job(job, "cron", hour=RUN_HOUR, minute=RUN_MINUTE)
    logger.info("스케줄러 시작: 매일 %02d:%02d(KST) 실행", RUN_HOUR, RUN_MINUTE)
    scheduler.start()


if __name__ == "__main__":
    main()
