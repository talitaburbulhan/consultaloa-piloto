from __future__ import annotations

import argparse
import json

from loa_api.database import SessionLocal
from loa_api.editorial_map import backfill_budget_record_classification, seed_editorial_map


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Carrega o mapa editorial e classifica registros de forma idempotente."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Confirma as alterações. Sem esta opção, a transação é revertida.",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        result = {
            "catalog": seed_editorial_map(db),
            "records": backfill_budget_record_classification(db),
            "applied": args.apply,
        }
        if args.apply:
            db.commit()
        else:
            db.rollback()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
