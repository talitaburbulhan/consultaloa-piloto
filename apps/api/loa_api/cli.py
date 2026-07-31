import argparse

from .config import get_settings
from .database import Base, SessionLocal, engine
from .ingestion import ingest_directory


def main() -> None:
    parser = argparse.ArgumentParser(description="Indexação rastreável dos PDFs das LOAs")
    parser.add_argument("--catalog-only", action="store_true", help="Não extrai o texto das páginas")
    parser.add_argument("--file", help="Processa somente um PDF do diretório de fontes")
    args = parser.parse_args()
    settings = get_settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if args.file:
            from .ingestion import ingest_pdf

            versions = [
                ingest_pdf(
                    db,
                    settings.source_dir / args.file,
                    include_text=not args.catalog_only,
                )
            ]
        else:
            versions = []
            paths = sorted(settings.source_dir.glob("*.pdf"))
            for position, path in enumerate(paths, start=1):
                from .ingestion import ingest_pdf

                versions.append(
                    ingest_pdf(db, path, include_text=not args.catalog_only)
                )
                print(f"[{position}/{len(paths)}] {path.name}", flush=True)
    print(f"{len(versions)} documentos processados.")


if __name__ == "__main__":
    main()
