from __future__ import annotations

import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_URL = "https://download.pytorch.org/tutorial/data.zip"
ARCHIVE_PATH = PROJECT_ROOT / "data.zip"
DATA_DIR = PROJECT_ROOT / "data"
NAMES_DIR = DATA_DIR / "names"


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading tutorial data from {DATA_URL}")
    try:
        urllib.request.urlretrieve(DATA_URL, ARCHIVE_PATH)
    except Exception as exc:
        print("Download failed.")
        print("Please manually download data.zip from the PyTorch char-rnn tutorial and extract data/names here:")
        print(NAMES_DIR)
        raise SystemExit(str(exc)) from exc

    with zipfile.ZipFile(ARCHIVE_PATH, "r") as archive:
        archive.extractall(PROJECT_ROOT)

    if not NAMES_DIR.exists():
        raise FileNotFoundError(f"Expected {NAMES_DIR}, but it was not created.")

    ARCHIVE_PATH.unlink(missing_ok=True)
    files = sorted(NAMES_DIR.glob("*.txt"))
    print(f"Done. {len(files)} language files are available in {NAMES_DIR}")


if __name__ == "__main__":
    main()
