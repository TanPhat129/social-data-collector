from apscheduler.schedulers.blocking import BlockingScheduler


def create_scheduler(timezone: str = "Asia/Ho_Chi_Minh") -> BlockingScheduler:
    return BlockingScheduler(timezone=timezone)
