"""
keep_alive.py – Запускает bot.py и перезапускает при падении.
Запустите ЭТОТ файл вместо bot.py для работы 24/7.
"""
import subprocess
import sys
import time
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler("C:\\xaut_bot\\bot.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

BOT_SCRIPT = "C:\\xaut_bot\\bot.py"
RESTART_DELAY = 10  # секунд

def main():
    attempt = 0
    while True:
        attempt += 1
        logger.info("=" * 50)
        logger.info("Запуск бота (попытка #%d) — %s", attempt, datetime.now())
        logger.info("=" * 50)

        try:
            proc = subprocess.run(
                [sys.executable, BOT_SCRIPT],
                cwd="C:\\xaut_bot",
            )
            logger.warning(
                "Бот завершился с кодом %d. Перезапуск через %d сек...",
                proc.returncode,
                RESTART_DELAY,
            )
        except Exception as exc:
            logger.error("Ошибка запуска: %s. Перезапуск через %d сек...", exc, RESTART_DELAY)

        time.sleep(RESTART_DELAY)

if __name__ == "__main__":
    main()
