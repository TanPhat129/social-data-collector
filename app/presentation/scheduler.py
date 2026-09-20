from app.core.container import Container
from app.scheduler.scheduler import create_scheduler
from app.presentation.cli import run_once


def run_scheduler(container: Container) -> None:
    scheduler = create_scheduler(container.settings.timezone)
    scheduler.add_job(
        run_once, "interval", args=[container],
        minutes=container.settings.collection_interval_minutes,
        id="collect-tutor-leads", replace_existing=True,
    )
    run_once(container)
    scheduler.start()
