"""Read-only host memory snapshots with a short shared sampling cache."""

import platform
import threading
import time
from datetime import datetime, timezone

import psutil


class SystemMonitor:
    def __init__(self):
        self._lock = threading.Lock()
        self._cached = None
        self._sampled_at = 0

    def snapshot(self):
        with self._lock:
            if self._cached is not None and time.monotonic() - self._sampled_at < 1:
                return self._cached
            memory = psutil.virtual_memory()
            try:
                swap_info = psutil.swap_memory()
                swap = {"available": True, "total": swap_info.total, "used": swap_info.used,
                        "free": swap_info.free, "percent": swap_info.percent}
            except (OSError, RuntimeError, psutil.Error):
                # Some Windows hosts disable the performance counters needed for swap.
                # RAM and process data remain useful; do not invent swap values.
                swap = {"available": False, "total": None, "used": None, "free": None, "percent": None}
            processes = []
            skipped = 0
            for process in psutil.process_iter(["pid", "name", "memory_info"], ad_value=None):
                try:
                    info = process.info
                    usage = info["memory_info"]
                    if usage is None:
                        skipped += 1
                        continue
                    if info["pid"] == 0:
                        continue
                    processes.append({"pid": info["pid"], "name": info["name"] or "Unknown process",
                                      "rss": usage.rss, "vms": usage.vms,
                                      "percent": usage.rss / memory.total * 100})
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    skipped += 1
            processes.sort(key=lambda p: (-p["rss"], p["pid"]))
            used = memory.total - memory.available
            snapshot = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "system": {"name": platform.node(), "os": platform.system(), "release": platform.release(),
                           "cpu_count": psutil.cpu_count(), "boot_time": psutil.boot_time()},
                "memory": {"total": memory.total, "available": memory.available, "used": used,
                           "free": memory.free, "percent": used / memory.total * 100},
                "swap": swap,
                "processes": processes, "process_count": len(processes), "skipped_processes": skipped,
            }
            self._cached = snapshot
            self._sampled_at = time.monotonic()
            return snapshot
