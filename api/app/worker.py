import logging

from rq import Worker

from app.services.job_queue import QUEUE_NAME, recover_stale_jobs, redis_connection, rpgforge_queue

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("rpgforge.worker")


def main() -> None:
    connection = redis_connection()
    queue = rpgforge_queue(connection)
    recovered = recover_stale_jobs(connection)
    logger.info(
        "RPGForge worker started. queue=%s recovered_running=%s recovered_pending=%s",
        QUEUE_NAME,
        recovered["running_timeout"],
        recovered["pending_missing"],
    )
    Worker([queue], connection=connection).work(with_scheduler=False)


if __name__ == "__main__":
    main()
