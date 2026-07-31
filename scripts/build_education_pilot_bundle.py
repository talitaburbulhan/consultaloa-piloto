"""Cria um pacote implantável do piloto de Educação sem alterar o acervo principal."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import zipfile
from pathlib import Path


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return bool(
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
    )


def build_bundle(source_db: Path, source_pdfs: Path, output: Path) -> dict[str, int]:
    if not source_db.is_file():
        raise RuntimeError(f"Banco de origem não encontrado: {source_db}")
    if not source_pdfs.is_dir():
        raise RuntimeError(f"Pasta de PDFs não encontrada: {source_pdfs}")

    output.mkdir(parents=True, exist_ok=True)
    data_dir = output / "dados"
    data_dir.mkdir(exist_ok=True)
    pilot_db = output / "loa.db"
    if pilot_db.exists():
        pilot_db.unlink()

    source = sqlite3.connect(source_db)
    target = sqlite3.connect(pilot_db)
    source.backup(target)
    source.close()
    target.execute("PRAGMA foreign_keys = ON")

    if not table_exists(target, "budget_records"):
        raise RuntimeError("O banco de origem não contém registros orçamentários.")

    target.execute(
        "CREATE TEMP TABLE pilot_pages AS "
        "SELECT DISTINCT page_id FROM budget_records "
        "WHERE parent_organization_code = '26000'"
    )
    target.execute(
        "DELETE FROM budget_records WHERE parent_organization_code IS NULL "
        "OR parent_organization_code != '26000'"
    )
    if table_exists(target, "chunks"):
        target.execute("DELETE FROM chunks WHERE page_id NOT IN (SELECT page_id FROM pilot_pages)")
    target.execute("DELETE FROM pages WHERE id NOT IN (SELECT page_id FROM pilot_pages)")
    target.execute(
        "DELETE FROM document_versions WHERE id NOT IN (SELECT DISTINCT version_id FROM pages)"
    )
    target.execute(
        "DELETE FROM documents WHERE id NOT IN (SELECT DISTINCT document_id FROM document_versions)"
    )
    for table in ("feedback", "audit_logs", "saved_queries"):
        if table_exists(target, table):
            target.execute(f"DELETE FROM {table}")

    filenames = [
        row[0]
        for row in target.execute(
            "SELECT DISTINCT filename FROM document_versions ORDER BY filename"
        )
    ]
    record_count = target.execute("SELECT COUNT(*) FROM budget_records").fetchone()[0]
    page_count = target.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
    target.commit()
    target.execute("VACUUM")
    target.close()

    copied = 0
    for filename in filenames:
        source_pdf = source_pdfs / filename
        if not source_pdf.is_file():
            raise RuntimeError(f"PDF obrigatório do piloto não encontrado: {source_pdf}")
        shutil.copy2(source_pdf, data_dir / filename)
        copied += 1

    archive = output / "loa-piloto-educacao-render.zip"
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.write(pilot_db, "loa.db")
        for pdf in sorted(data_dir.glob("*.pdf")):
            bundle.write(pdf, pdf.relative_to(output).as_posix())

    return {
        "budget_records": record_count,
        "pages": page_count,
        "pdfs": copied,
        "archive_bytes": archive.stat().st_size,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument("--source-pdfs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(build_bundle(args.source_db, args.source_pdfs, args.output))


if __name__ == "__main__":
    main()
