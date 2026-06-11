import json
import os
import subprocess
import sys
from pathlib import Path


def test_celery_app_bootstrap_registers_periodic_schedule():
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.setdefault("ENV", "test")

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json; "
                "from celery_workers.celery_app import celery_app; "
                "print(json.dumps(sorted(celery_app.conf.beat_schedule.keys())))"
            ),
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    schedule_keys = json.loads(result.stdout.strip().splitlines()[-1])

    assert "scan-scheduled-posts" in schedule_keys
    assert "poll-processing-posts" in schedule_keys
    assert "spawn-recurring-instances" in schedule_keys
    assert "collect-analytics-24h" in schedule_keys
    assert "send-grace-period-reminders" in schedule_keys
