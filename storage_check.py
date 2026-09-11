#!/usr/bin/env python3
"""Schreibt Speicher-Kennzahlen des Docker-Hosts nach data-dev/storage.json.

Läuft per Cron auf dem Host; das Backend liest die Datei aus dem gemounteten
Volume (/app/data) fuer die Storage-Kachel auf der Startseite.
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

DEFAULT_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data-dev", "storage.json")
OUT = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
GB = 1024 ** 3
UNITS = {
    "B": 1e-9, "KB": 1e-6, "MB": 1e-3, "GB": 1.0, "TB": 1e3,
    "KIB": 1.0 / (1024 * 1024), "MIB": 1.0 / 1024, "GIB": 1.0, "TIB": 1024.0,
}


def parse_size(text):
    """'17.22GB (89%)' -> 17.22 ; '0B' -> 0.0 ; '' -> None"""
    m = re.search(r"([\d.]+)\s*([KMGTP]?i?B)\b", text or "", re.I)
    if not m:
        return None
    return round(float(m.group(1)) * UNITS.get(m.group(2).upper(), 1.0), 2)


def main():
    u = shutil.disk_usage("/")
    data = {
        "ts": datetime.datetime.now().isoformat(sep=" ", timespec="minutes"),
        "host": os.uname().nodename,
        "disk": {
            "total_gb": round(u.total / GB, 1),
            "used_gb": round(u.used / GB, 1),
            "free_gb": round(u.free / GB, 1),
            "percent": round(u.used / u.total * 100, 1),
        },
    }
    try:
        r = subprocess.run(
            ["docker", "system", "df", "--format", "{{.Type}}|{{.Size}}|{{.Reclaimable}}"],
            capture_output=True, text=True, timeout=60,
        )
        docker = {}
        for line in r.stdout.strip().splitlines():
            parts = line.split("|")
            if len(parts) < 2:
                continue
            key = parts[0].strip().lower().replace(" ", "_")
            reclaim = parts[2] if len(parts) > 2 else ""
            pct = re.search(r"\((\d+)%\)", reclaim)
            docker[key] = {
                "size_gb": parse_size(parts[1]),
                "reclaimable_gb": parse_size(reclaim),
                "reclaimable_percent": int(pct.group(1)) if pct else None,
            }
        data["docker"] = docker
    except Exception as exc:  # noqa: BLE001
        data["docker_error"] = str(exc)

    tmp = OUT + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh, indent=1)
    os.replace(tmp, OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
