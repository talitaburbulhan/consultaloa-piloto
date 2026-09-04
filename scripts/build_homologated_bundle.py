"""Build and validate the deployable bundle of homologated LOA data.

The source database is never modified. Feedback and other operational data are
not copied into the release database; the production feedback PostgreSQL
database remains an independent service.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter


RELEASE_DATABASE = "loa.db"
RELEASE_ARCHIVE = "loa-homologada-render.zip"
MANIFEST_NAME = "manifest.json"
OPERATIONAL_TABLES = (
    "audit_logs",
    "feedback",
    "ingestion_errors",
    "ingestion_runs",
    "saved_queries",
)


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return bool(
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scalar(connection: sqlite3.Connection, statement: str) -> int:
    return int(connection.execute(statement).fetchone()[0])


def _prepare_database(source_db: Path, target_db: Path) -> dict:
    source = sqlite3.connect(f"file:{source_db.resolve().as_posix()}?mode=ro", uri=True)
    target = sqlite3.connect(target_db)
    try:
        source.backup(target)
        target.execute("PRAGMA foreign_keys = ON")
        required = {
            "budget_records",
            "pages",
            "document_versions",
            "documents",
            "editorial_areas",
            "editorial_rules",
            "historical_segments",
        }
        missing = sorted(table for table in required if not table_exists(target, table))
        if missing:
            raise RuntimeError("Tabelas obrigatórias ausentes: " + ", ".join(missing))

        source_records = scalar(target, "SELECT COUNT(*) FROM budget_records")
        homologated_records = scalar(
            target,
            "SELECT COUNT(*) FROM budget_records WHERE evidence_status = 'homologated'",
        )
        if homologated_records == 0:
            raise RuntimeError("Nenhum registro homologado foi encontrado.")

        target.execute(
            "CREATE TEMP TABLE release_pages AS "
            "SELECT DISTINCT page_id FROM budget_records "
            "WHERE evidence_status = 'homologated'"
        )
        target.execute("DELETE FROM budget_records WHERE evidence_status != 'homologated' OR evidence_status IS NULL")
        for table in ("chunks", "content_blocks"):
            if table_exists(target, table):
                target.execute(
                    f"DELETE FROM {table} WHERE page_id NOT IN (SELECT page_id FROM release_pages)"
                )
        target.execute("DELETE FROM pages WHERE id NOT IN (SELECT page_id FROM release_pages)")
        target.execute(
            "DELETE FROM document_versions WHERE id NOT IN "
            "(SELECT DISTINCT version_id FROM pages)"
        )
        target.execute(
            "DELETE FROM documents WHERE id NOT IN "
            "(SELECT DISTINCT document_id FROM document_versions)"
        )
        for table in OPERATIONAL_TABLES:
            if table_exists(target, table):
                target.execute(f"DELETE FROM {table}")
        target.commit()

        foreign_key_errors = target.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_errors:
            raise RuntimeError(f"Falha de integridade referencial: {foreign_key_errors[:5]}")
        integrity = target.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"Falha no PRAGMA integrity_check: {integrity}")

        document_pages: dict[str, list[int]] = {}
        for filename, page_number in target.execute(
            "SELECT document_versions.filename, pages.pdf_page_number "
            "FROM document_versions JOIN pages ON pages.version_id = document_versions.id "
            "ORDER BY document_versions.filename, pages.pdf_page_number"
        ):
            document_pages.setdefault(filename, []).append(int(page_number))
        filenames = [
            row[0]
            for row in target.execute(
                "SELECT filename FROM document_versions ORDER BY filename"
            )
        ]
        areas = {
            row[0]: row[1]
            for row in target.execute(
                "SELECT area_slug, COUNT(*) FROM budget_records "
                "GROUP BY area_slug ORDER BY area_slug"
            )
        }
        stats = {
            "source_records": source_records,
            "excluded_unhomologated_records": source_records - homologated_records,
            "budget_records": homologated_records,
            "pages": scalar(target, "SELECT COUNT(*) FROM pages"),
            "document_versions": scalar(target, "SELECT COUNT(*) FROM document_versions"),
            "editorial_areas": scalar(target, "SELECT COUNT(*) FROM editorial_areas"),
            "editorial_rules": scalar(target, "SELECT COUNT(*) FROM editorial_rules WHERE active = 1"),
            "historical_segments": scalar(target, "SELECT COUNT(*) FROM historical_segments"),
            "areas": areas,
            "filenames": filenames,
            "document_pages": document_pages,
        }
    finally:
        source.close()
        target.close()

    vacuum = sqlite3.connect(target_db)
    try:
        vacuum.execute("VACUUM")
    finally:
        vacuum.close()
    return stats


def _write_sparse_pdf(source: Path, target: Path, retained_pages: list[int]) -> None:
    """Keep cited pages at their original one-based PDF positions.

    Non-cited pages up to the last cited page become small blank placeholders,
    so existing ``#page=N`` links continue to point to the documentary page.
    """
    reader = PdfReader(source)
    retained = set(retained_pages)
    if not retained or min(retained) < 1 or max(retained) > len(reader.pages):
        raise RuntimeError(
            f"Numeração de página inválida em {source.name}: {retained_pages[:5]}"
        )
    writer = PdfWriter()
    first = reader.pages[0]
    default_width = float(first.mediabox.width)
    default_height = float(first.mediabox.height)
    for page_number in range(1, max(retained) + 1):
        if page_number in retained:
            writer.add_page(reader.pages[page_number - 1])
        else:
            writer.add_blank_page(width=default_width, height=default_height)
    with target.open("wb") as stream:
        writer.write(stream)


def build_bundle(source_db: Path, source_pdfs: Path, output: Path) -> dict:
    if not source_db.is_file():
        raise RuntimeError(f"Banco de origem não encontrado: {source_db}")
    if not source_pdfs.is_dir():
        raise RuntimeError(f"Pasta de PDFs não encontrada: {source_pdfs}")

    output.mkdir(parents=True, exist_ok=True)
    archive_path = output / RELEASE_ARCHIVE
    manifest_path = output / MANIFEST_NAME

    with tempfile.TemporaryDirectory(prefix="loa-release-", dir=output) as temp_name:
        stage = Path(temp_name)
        target_db = stage / RELEASE_DATABASE
        data_dir = stage / "dados"
        data_dir.mkdir()
        stats = _prepare_database(source_db, target_db)

        filenames = stats.pop("filenames")
        document_pages = stats.pop("document_pages")
        pdf_entries = []
        for filename in filenames:
            source_pdf = source_pdfs / filename
            if not source_pdf.is_file():
                raise RuntimeError(f"PDF homologado obrigatório não encontrado: {source_pdf}")
            copied = data_dir / filename
            retained_pages = document_pages[filename]
            _write_sparse_pdf(source_pdf, copied, retained_pages)
            pdf_entries.append(
                {
                    "filename": filename,
                    "bytes": copied.stat().st_size,
                    "sha256": sha256(copied),
                    "source_bytes": source_pdf.stat().st_size,
                    "source_sha256": sha256(source_pdf),
                    "retained_pages": retained_pages,
                    "last_retained_page": max(retained_pages),
                }
            )

        manifest = {
            "format": "consulta-loa-homologated-bundle-v1",
            "database": {
                "filename": RELEASE_DATABASE,
                "bytes": target_db.stat().st_size,
                "sha256": sha256(target_db),
            },
            "statistics": stats,
            "pdfs": pdf_entries,
            "feedback_storage": "external-postgresql-not-included",
        }
        staged_manifest = stage / MANIFEST_NAME
        staged_manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        temporary_archive = output / f".{RELEASE_ARCHIVE}.tmp"
        if temporary_archive.exists():
            temporary_archive.unlink()
        with zipfile.ZipFile(
            temporary_archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as bundle:
            bundle.write(target_db, RELEASE_DATABASE)
            bundle.write(staged_manifest, MANIFEST_NAME)
            for pdf in sorted(data_dir.glob("*.pdf")):
                bundle.write(pdf, pdf.relative_to(stage).as_posix())
        temporary_archive.replace(archive_path)
        shutil.copy2(staged_manifest, manifest_path)

    validation = validate_bundle(archive_path, source_pdfs)
    return {
        **stats,
        "pdfs": len(pdf_entries),
        "archive": str(archive_path),
        "archive_bytes": archive_path.stat().st_size,
        "archive_sha256": sha256(archive_path),
        "validation": validation,
    }


def validate_bundle(archive_path: Path, source_pdfs: Path | None = None) -> dict:
    if not archive_path.is_file():
        raise RuntimeError(f"Pacote não encontrado: {archive_path}")
    with tempfile.TemporaryDirectory(prefix="loa-validate-") as temp_name:
        target = Path(temp_name)
        with zipfile.ZipFile(archive_path) as bundle:
            bad_member = bundle.testzip()
            if bad_member:
                raise RuntimeError(f"Entrada ZIP corrompida: {bad_member}")
            bundle.extractall(target)
        manifest = json.loads((target / MANIFEST_NAME).read_text(encoding="utf-8"))
        database = target / RELEASE_DATABASE
        if sha256(database) != manifest["database"]["sha256"]:
            raise RuntimeError("Hash do banco não corresponde ao manifesto.")
        verified_source_pages = 0
        for item in manifest["pdfs"]:
            pdf = target / "dados" / item["filename"]
            if not pdf.is_file() or sha256(pdf) != item["sha256"]:
                raise RuntimeError(f"PDF ausente ou divergente: {item['filename']}")
            sparse_reader = PdfReader(pdf)
            if len(sparse_reader.pages) != item["last_retained_page"]:
                raise RuntimeError(f"Numeração esparsa divergente: {item['filename']}")
            if source_pdfs is not None:
                original = source_pdfs / item["filename"]
                if not original.is_file() or sha256(original) != item["source_sha256"]:
                    raise RuntimeError(f"Origem ausente ou divergente: {item['filename']}")
                source_reader = PdfReader(original)
                for page_number in item["retained_pages"]:
                    source_page = source_reader.pages[page_number - 1]
                    sparse_page = sparse_reader.pages[page_number - 1]
                    source_content = source_page.get_contents()
                    sparse_content = sparse_page.get_contents()
                    if (source_content.get_data() if source_content else b"") != (
                        sparse_content.get_data() if sparse_content else b""
                    ):
                        raise RuntimeError(
                            f"Conteúdo divergente em {item['filename']} página {page_number}"
                        )
                    verified_source_pages += 1

        connection = sqlite3.connect(database)
        try:
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Banco extraído falhou no teste de integridade.")
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError("Banco extraído contém referências inválidas.")
            non_homologated = scalar(
                connection,
                "SELECT COUNT(*) FROM budget_records "
                "WHERE evidence_status != 'homologated' OR evidence_status IS NULL",
            )
            operational_rows = {
                table: scalar(connection, f"SELECT COUNT(*) FROM {table}")
                for table in OPERATIONAL_TABLES
                if table_exists(connection, table)
            }
        finally:
            connection.close()
        if non_homologated:
            raise RuntimeError("O pacote contém registros não homologados.")
        if any(operational_rows.values()):
            raise RuntimeError(f"O pacote contém dados operacionais: {operational_rows}")
        return {
            "zip": "ok",
            "sqlite": "ok",
            "hashes": "ok",
            "source_page_content": "ok" if source_pdfs is not None else "not_checked",
            "verified_source_pages": verified_source_pages,
            "non_homologated_records": non_homologated,
            "operational_rows": operational_rows,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", type=Path)
    parser.add_argument("--source-pdfs", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate", type=Path, help="Valida um pacote já construído.")
    args = parser.parse_args()
    if args.validate:
        result = validate_bundle(args.validate, args.source_pdfs)
    else:
        if not all((args.source_db, args.source_pdfs, args.output)):
            parser.error("--source-db, --source-pdfs e --output são obrigatórios")
        result = build_bundle(args.source_db, args.source_pdfs, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
