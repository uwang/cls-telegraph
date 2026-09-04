"""Daily archive worker; explicit arguments are passed through to the CLI."""
import os
import fcntl
import logging
import signal
import subprocess
import sys
import tempfile
import threading
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .bark import bark_config, deliver_pending
from .storage import connect, finish_archive, show_status, start_archive


def latest_due(now, scheduled):
    return now.date() - timedelta(days=1 if now.time() >= scheduled else 2)


def archive(day, output):
    # Publish only a fully successful download, leaving existing archives intact.
    with tempfile.TemporaryDirectory(prefix=".archive-", dir=output) as staging:
        subprocess.run([
            "cls-telegraph", "--archive", "--date", day.isoformat(),
            "--output-dir", staging,
        ], check=True, timeout=3600)
        relative = Path(f"{day:%Y/%m/%Y-%m-%d}.md")
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(Path(staging) / relative, target)
    print(f"归档完成: {target}", flush=True)
    return target


def main():
    if len(sys.argv) > 1 and sys.argv[1:] != ["--status"]:
        os.execvp("cls-telegraph", ["cls-telegraph", *sys.argv[1:]])
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    zone = ZoneInfo(os.environ.get("TZ", "Asia/Shanghai"))
    scheduled = time.fromisoformat(os.environ.get("ARCHIVE_TIME", "00:10"))
    push_time = time.fromisoformat(os.environ.get("BARK_PUSH_TIME", "08:00"))
    output = Path(os.environ.get("OUTPUT_DIR", "/data"))
    output.mkdir(parents=True, exist_ok=True)
    db = connect(output / "archive.sqlite3")
    if sys.argv[1:] == ["--status"]:
        show_status(db)
        return
    # One scheduler per archive directory, including separate Compose projects.
    lock = (output / ".archive.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    endpoint, devices = bark_config(os.environ)
    logging.info("Bark 配置设备数: %s", len(devices))
    retry_seconds = int(os.environ.get("ARCHIVE_RETRY_SECONDS", "300"))
    push_retry_seconds = int(os.environ.get("BARK_RETRY_SECONDS", "900"))
    if min(retry_seconds, push_retry_seconds) <= 0:
        raise ValueError("重试间隔必须大于 0")
    state = output / ".archive-last-success"
    saved = db.execute("SELECT value FROM meta WHERE key='last_success'").fetchone()
    last = date.fromisoformat(saved[0]) if saved else None
    if last is None and state.exists():
        last = date.fromisoformat(state.read_text().strip())
        with db:
            db.execute("INSERT INTO meta VALUES('last_success', ?)", (last.isoformat(),))
    with db:
        db.execute("UPDATE archive_log SET status='interrupted',finished_at=? WHERE status='running'",
                   (datetime.now().timestamp(),))
    stopped = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopped.set())
    logging.info("每日 %s (%s) 归档前一天电报，目录: %s", scheduled, zone, output)
    next_archive = 0
    while not stopped.is_set():
        now = datetime.now(zone)
        due = latest_due(now, scheduled)
        day = last + timedelta(days=1) if last else due
        ready = last is not None or now.time() >= scheduled
        if ready and day <= due and now.timestamp() >= next_archive:
            attempt = start_archive(db, day)
            try:
                path = archive(day, output)
                finish_archive(db, attempt, day, devices, path=path)
                last = day
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                # Store a safe diagnostic without subprocess output or credentials.
                error = type(exc).__name__
                if isinstance(exc, subprocess.CalledProcessError):
                    error += f" (exit={exc.returncode})"
                finish_archive(db, attempt, day, devices, error=error)
                logging.error("归档 %s 失败: %s", day, error)
                next_archive = datetime.now().timestamp() + retry_seconds
        # Check again after a potentially long archive; overnight pending pushes wait until morning.
        if datetime.now(zone).time() >= push_time:
            deliver_pending(db, endpoint, devices, stopped, push_retry_seconds)
        stopped.wait(1 if last and last < due else 30)


if __name__ == "__main__":
    main()
