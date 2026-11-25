"""Download the UCI "Diabetes 130-US Hospitals for Years 1999-2008" dataset.

Source: https://archive.ics.uci.edu/dataset/296  (DOI 10.24432/C5230J, CC BY 4.0)
The zip (~3 MB) is saved to data/raw/ and extracted there. The SHA-256 of the two
CSV files we use is checked so that everyone evaluates on identical data.

Usage:  python scripts/download_data.py
"""
from __future__ import annotations

import hashlib
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

URL = "https://archive.ics.uci.edu/static/public/296/diabetes+130-us+hospitals+for+years+1999-2008.zip"
RAW = Path(__file__).resolve().parents[1] / "data" / "raw"

# Filled in from the copy used for the published evaluation (2026-11-25).
EXPECTED_SHA256 = {
    "diabetic_data.csv": "0689e7ec031237dc63031b938805c48377748761a3b26acab621567afa24df97",
    "IDS_mapping.csv": "f1bb82b471cb34649352597572c9b1fb00bd27f77b9f5a22a03dc3eb1039749e",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    if not (RAW / "diabetic_data.csv").exists():
        print(f"Downloading {URL}")
        req = urllib.request.Request(URL, headers={"User-Agent": "callfirst-research-script"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            blob = resp.read()
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            for name in zf.namelist():
                base = Path(name).name
                if base in EXPECTED_SHA256:
                    (RAW / base).write_bytes(zf.read(name))
    ok = True
    for name, expected in EXPECTED_SHA256.items():
        path = RAW / name
        if not path.exists():
            print(f"MISSING {path}")
            ok = False
            continue
        got = sha256(path)
        status = "ok" if got == expected else "MISMATCH"
        if got != expected:
            ok = False
        print(f"{status:8s} {name}  sha256={got}")
    if not ok:
        print("Checksum mismatch or missing file: results may differ from reports/metrics.json")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
