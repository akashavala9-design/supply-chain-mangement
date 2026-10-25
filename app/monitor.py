import os
import time
import logging

from app.dq import run_checks
from app.quarantine import quarantine_invalid_shipments

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

INTERVAL_SECONDS = int(os.getenv("GUARD_INTERVAL_SECONDS", "300"))


def monitor_once():
    report = run_checks()
    quarantine_result = quarantine_invalid_shipments()

    logging.info(
        "Data-quality checks=%s, issues=%s, new quarantined records=%s",
        report["total_checks"],
        sum(1 for issue in report["issues"]
            if issue["rows_affected"] > 0),
        quarantine_result["new_records"],
    )

    return {
        "checks": report["total_checks"],
        "quarantine": quarantine_result,
    }


def run_forever():
    logging.info(
        "Quarantine Guard monitor started; interval=%s seconds",
        INTERVAL_SECONDS,
    )

    while True:
        try:
            monitor_once()
        except Exception:
            logging.exception("Quarantine Guard monitoring cycle failed")

        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    run_forever()
