import logging
import time

from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("rpgforge.worker")


def main() -> None:
    logger.info("RPGForge worker placeholder started. redis_url=%s", settings.redis_url)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
