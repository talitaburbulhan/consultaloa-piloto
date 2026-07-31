import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from sqlalchemy import select

from loa_api.config import get_settings
from loa_api.database import SessionLocal
from loa_api.models import DocumentVersion, Page


def pending_inventory_indices(inventory: list[dict]) -> list[int]:
    pending = []
    with SessionLocal() as db:
        for index, row in enumerate(inventory):
            version = db.scalar(
                select(DocumentVersion).where(DocumentVersion.filename == row["document"])
            )
            method = db.scalar(
                select(Page.extraction_method).where(
                    Page.version_id == version.id,
                    Page.pdf_page_number == row["pdf_page"],
                )
            )
            if method == "ocr-pending":
                pending.append(index)
    return pending


def acquire_lock(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            pid = int(path.read_text(encoding="ascii").strip())
            os.kill(pid, 0)
        except (OSError, ValueError):
            path.unlink(missing_ok=True)
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        else:
            raise SystemExit(f"OCR contínuo já está ativo no processo {pid}.")
    with os.fdopen(descriptor, "w", encoding="ascii") as stream:
        stream.write(str(os.getpid()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--pause-seconds", type=int, default=5)
    parser.add_argument("--include-review", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    settings = get_settings()
    log_dir = settings.storage_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    lock = log_dir / "ocr-continuous.lock"
    acquire_lock(lock)

    try:
        inventory_path = settings.storage_dir / "homologation" / "pending-pages.jsonl"
        allowed = {"ocr-required"}
        if args.include_review:
            allowed.update({"visual-review", "vector-or-blank-review"})
        inventory = [
            json.loads(line)
            for line in inventory_path.read_text(encoding="utf-8").splitlines()
            if json.loads(line)["classification"] in allowed
        ]
        while True:
            pending = pending_inventory_indices(inventory)
            if not pending:
                print("OCR_REQUIRED_COMPLETE", flush=True)
                break
            offset = pending[0]
            print(
                json.dumps(
                    {"pending_ocr": len(pending), "offset": offset, "batch": args.batch_size}
                ),
                flush=True,
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(root / "scripts" / "ocr_pending_pages.py"),
                    "--offset",
                    str(offset),
                    "--limit",
                    str(args.batch_size),
                ] + (["--include-review"] if args.include_review else []),
                cwd=root,
                check=False,
            )
            if completed.returncode:
                print(f"BATCH_FAILED returncode={completed.returncode}", flush=True)
                time.sleep(60)
            else:
                time.sleep(args.pause_seconds)
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
