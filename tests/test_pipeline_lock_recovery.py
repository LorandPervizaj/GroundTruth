import json
import os
import signal
import subprocess
import sys

import pytest

from groundtruth.automation.state import PipelineLock


def test_stale_metadata_is_not_a_lock(tmp_path):
    path = tmp_path / "weekly.lock"
    path.write_text('{"pid": 123, "run_id": "interrupted"}')
    with PipelineLock(path, "new"):
        pass
    metadata = json.loads(path.read_text())
    assert metadata["pid"] == os.getpid()
    assert metadata["run_id"] == "new"
    assert metadata["host"]


def test_process_death_releases_lock(tmp_path):
    path = tmp_path / "weekly.lock"
    script = (
        "import sys,time,os; from pathlib import Path; "
        "from groundtruth.automation.state import PipelineLock; "
        "lock=PipelineLock(Path(sys.argv[1]),'child'); lock.__enter__(); "
        "print(os.getpid(),flush=True); time.sleep(60)"
    )
    process = subprocess.Popen([sys.executable, "-c", script, str(path)], stdout=subprocess.PIPE)
    try:
        child_pid = int(process.stdout.readline().strip())
        with pytest.raises(RuntimeError), PipelineLock(path, "overlap"):
            pass
        os.kill(child_pid, signal.SIGTERM)
        process.wait(timeout=10)
        with PipelineLock(path, "recovered"):
            pass
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)


def test_cancellation_releases_lock(tmp_path):
    path = tmp_path / "weekly.lock"
    with pytest.raises(KeyboardInterrupt), PipelineLock(path, "cancelled"):
        raise KeyboardInterrupt
    with PipelineLock(path, "retry"):
        pass
