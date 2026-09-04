from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from loa_api.database import Base
from loa_api.editorial_map import (
    active_rules_for,
    backfill_budget_record_classification,
    canonical_area_totals,
    classify_budget_record,
    historical_comparison_plan,
    resolve_area_alias,
    resolve_historical_entity_alias,
    seed_editorial_map,
)
from loa_api.models import BudgetRecord, Document, DocumentKind, DocumentVersion, Page
from loa_api.schemas import SearchRequest
from loa_api.search import _query_years, _value_sort_direction, search_documents


def make_record(**overrides) -> BudgetRecord:
    values = {
        "year": 2024,
        "document_version_id": 1,
        "page_id": 1,
        "organization_code": "74000",
        "organization_name": "Operações Oficiais de Crédito",
        "parent_organization_code": "74000",
        "original_value": "100",
        "numeric_value": Decimal("100"),
        "unit": "R$ 1,00",
        "source_text": "evidência",
        "deduplication_key": "x" * 64,
    }
    values.update(overrides)
    return BudgetRecord(**values)


def test_classifies_root_total_without_summing_components() -> None:
    result = classify_budget_record(make_record())
    assert result.area_slug == "fiscal_74000"
    assert result.record_level == "total_orgao"
    assert result.aggregation_policy == "canonical"


def test_protected_code_override_wins_over_fiscal_parent() -> None:
    result = classify_budget_record(
        make_record(organization_code="74202", parent_organization_code="74000")
    )
    assert result.area_slug == "saude"
    assert result.record_level == "subtotal_unidade"


def test_program_and_supervised_levels_are_not_canonical_totals() -> None:
    program = classify_budget_record(
        make_record(organization_code=None, program_code="6012", parent_organization_code="defesa")
    )
    supervised = classify_budget_record(
        make_record(
            organization_code="93452",
            institution_category="programacao_condicionada_supervisionada",
            parent_organization_code="defesa",
        )
    )
    assert (program.record_level, program.aggregation_policy) == ("total_programa", "detail_only")
    assert (supervised.record_level, supervised.aggregation_policy) == (
        "programacao_supervisionada",
        "separate",
    )


def test_unknown_parent_is_blocked_instead_of_guessed() -> None:
    result = classify_budget_record(
        make_record(organization_code="99999", parent_organization_code=None)
    )
    assert result.area_slug is None
    assert result.evidence_status == "unclassified"
    assert result.aggregation_policy == "blocked"


def test_seed_and_backfill_are_idempotent() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(make_record())
        db.commit()
        first_catalog = seed_editorial_map(db)
        first_records = backfill_budget_record_classification(db)
        db.commit()
        second_catalog = seed_editorial_map(db)
        second_records = backfill_budget_record_classification(db)
        db.commit()
    assert first_catalog == second_catalog
    assert first_records["changed"] == 1
    assert second_records["changed"] == 0


def test_longest_area_alias_wins() -> None:
    assert resolve_area_alias("Mostre Operações Oficiais de Crédito de 2024") == (
        "fiscal_74000",
        "Operações Oficiais de Crédito",
    )


def test_canonical_area_totals_exclude_components_and_unclassified_records() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    root = make_record(deduplication_key="a" * 64)
    component = make_record(
        organization_code="74919",
        deduplication_key="b" * 64,
    )
    unknown = make_record(
        organization_code="99999",
        parent_organization_code=None,
        deduplication_key="c" * 64,
    )
    with Session(engine) as db:
        db.add_all([root, component, unknown])
        db.flush()
        backfill_budget_record_classification(db)
        records, missing = canonical_area_totals(db, "fiscal_74000", [2024, 2025])
    assert [record.organization_code for record in records] == ["74000"]
    assert missing == [2025]


def test_canonical_area_totals_reject_duplicate_years() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all(
            [
                make_record(deduplication_key="d" * 64),
                make_record(deduplication_key="e" * 64, original_value="101"),
            ]
        )
        db.flush()
        backfill_budget_record_classification(db)
        try:
            canonical_area_totals(db, "fiscal_74000", [2024])
        except ValueError as error:
            assert "2024" in str(error)
        else:
            raise AssertionError("Totais canônicos duplicados deveriam ser recusados")


def test_search_uses_only_canonical_area_total() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        document = Document(
            year=2024,
            title="LOA 2024 — Operações Oficiais de Crédito",
            kind=DocumentKind.VOLUME,
            official_url=None,
        )
        version = DocumentVersion(
            document=document,
            filename="2024_volume5.pdf",
            sha256="1" * 64,
            byte_size=100,
            page_count=2,
        )
        total_page = Page(
            version=version,
            pdf_page_number=1,
            printed_page_label="1",
            original_text="74000 Operações Oficiais de Crédito 2.232.495.842.780",
            page_sha256="2" * 64,
        )
        unit_page = Page(
            version=version,
            pdf_page_number=2,
            printed_page_label="2",
            original_text="74919 unidade integrante 100",
            page_sha256="3" * 64,
        )
        db.add_all([document, version, total_page, unit_page])
        db.flush()
        total = make_record(
            document_version_id=version.id,
            page_id=total_page.id,
            original_value="2.232.495.842.780",
            numeric_value=Decimal("2232495842780"),
            source_text=total_page.original_text,
            deduplication_key="4" * 64,
        )
        component = make_record(
            document_version_id=version.id,
            page_id=unit_page.id,
            organization_code="74919",
            original_value="100",
            numeric_value=Decimal("100"),
            source_text=unit_page.original_text,
            deduplication_key="5" * 64,
        )
        db.add_all([total, component])
        db.flush()
        seed_editorial_map(db)
        backfill_budget_record_classification(db)
        db.commit()

        response = search_documents(
            db,
            SearchRequest(
                query="Qual o orçamento de Operações Oficiais de Crédito em 2024?",
                interpretation_confirmed=True,
            ),
        )

    assert "R$ 2.232.495.842.780" in response.summary
    assert "100" not in response.summary
    assert response.sources[0].pdf_page == 1
    assert any("não foram somados" in item for item in response.limitations)


def test_search_refuses_to_construct_area_total_from_components() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        component = make_record(
            organization_code="74919",
            original_value="100",
            numeric_value=Decimal("100"),
            deduplication_key="6" * 64,
        )
        db.add(component)
        db.flush()
        seed_editorial_map(db)
        backfill_budget_record_classification(db)
        db.commit()

        response = search_documents(
            db,
            SearchRequest(
                query="Qual o orçamento de Operações Oficiais de Crédito em 2024?",
                interpretation_confirmed=True,
            ),
        )

    assert response.insufficient_evidence
    assert response.evidence == []
    assert "não há uma série de totais" in response.summary


def test_incra_plan_preserves_three_codes_and_discloses_changes() -> None:
    plan = historical_comparison_plan("incra", list(range(2019, 2027)))
    assert [segment["organization_code"] for segment in plan.segments] == [
        "20201",
        "22201",
        "49201",
    ]
    assert plan.code_changes == ((2020, "20201", "22201"), (2024, "22201", "49201"))
    assert plan.missing_years == ()
    assert plan.direct_comparison_allowed
    assert not plan.aggregation_allowed


def test_abgf_plan_exposes_documentary_gaps_instead_of_zeroes() -> None:
    plan = historical_comparison_plan("abgf", list(range(2019, 2027)))
    assert plan.missing_years == (2021, 2022)
    assert any("Ausência documental" in warning for warning in plan.warnings)


def test_inb_regime_break_blocks_direct_comparison() -> None:
    plan = historical_comparison_plan("inb", list(range(2019, 2027)))
    assert not plan.direct_comparison_allowed
    assert not plan.aggregation_allowed
    assert any("regime orçamentário" in warning for warning in plan.warnings)
    assert {segment["entity_slug"] for segment in plan.segments} == {
        "inb_fiscal",
        "inb_investimento",
    }


def test_historical_alias_resolution_uses_longest_match() -> None:
    assert resolve_historical_entity_alias(
        "Mostre a série do Fundo da Marinha Mercante de 2019 a 2026"
    ) == ("fmm", "Fundo da Marinha Mercante")


def test_subject_rules_include_global_and_specific_safeguards() -> None:
    rules = active_rules_for("tourism")
    keys = {rule["rule_key"] for rule in rules}
    assert "no_cross_level_sum" in keys
    assert "absence_is_not_zero" in keys
    assert "tourism_perimeter" in keys


def test_historical_plan_rejects_overlapping_segments() -> None:
    catalog = {
        "historical_entities": {"x": {"label": "X", "aliases": ["X"]}},
        "historical_segments": [
            {
                "entity_slug": "x_old",
                "area_slug": "x",
                "organization_code": "1",
                "start_year": 2019,
                "end_year": 2021,
                "comparison_group": "x",
            },
            {
                "entity_slug": "x_new",
                "area_slug": "x",
                "organization_code": "2",
                "start_year": 2021,
                "end_year": 2022,
                "comparison_group": "x",
            },
        ],
        "rules": [],
    }
    try:
        historical_comparison_plan("x", [2019, 2020, 2021, 2022], catalog)
    except ValueError as error:
        assert "2021" in str(error)
    else:
        raise AssertionError("Segmentos sobrepostos deveriam bloquear o plano")


def test_search_returns_historical_series_with_original_codes() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for index, (year, code, value) in enumerate(
            [(2019, "20201", "1.000"), (2020, "22201", "2.000")], start=1
        ):
            document = Document(
                year=year,
                title=f"LOA {year}",
                kind=DocumentKind.VOLUME,
                official_url=None,
            )
            version = DocumentVersion(
                document=document,
                filename=f"{year}_volume4.pdf",
                sha256=str(index) * 64,
                byte_size=100,
                page_count=1,
            )
            page = Page(
                version=version,
                pdf_page_number=10,
                printed_page_label="9",
                original_text=f"{code} INCRA {value}",
                page_sha256=str(index + 2) * 64,
            )
            db.add_all([document, version, page])
            db.flush()
            db.add(
                make_record(
                    year=year,
                    document_version_id=version.id,
                    page_id=page.id,
                    organization_code=code,
                    organization_name="INCRA",
                    parent_organization_code="agricultura_desenvolvimento_agrario_pesca",
                    original_value=value,
                    numeric_value=Decimal(value.replace(".", "")),
                    source_text=page.original_text,
                    deduplication_key=str(index + 4) * 64,
                )
            )
        db.flush()
        seed_editorial_map(db)
        backfill_budget_record_classification(db)
        db.commit()

        response = search_documents(
            db,
            SearchRequest(
                query="Mostre a série histórica documental do INCRA de 2019 a 2020",
                years=[2019, 2020],
                interpretation_confirmed=True,
            ),
        )

    assert "2019 (código 20201): R$ 1.000" in response.summary
    assert "2020 (código 22201): R$ 2.000" in response.summary
    assert "2020: 20201 → 22201" in response.summary
    assert not response.insufficient_evidence
    assert len(response.sources) == 2


def test_year_range_is_expanded_inclusively() -> None:
    assert _query_years("Mostre os dados de 2023 a 2026", []) == [
        2023,
        2024,
        2025,
        2026,
    ]
    assert _query_years("Compare entre 2020 e 2023", []) == [
        2020,
        2021,
        2022,
        2023,
    ]
    assert _query_years("Mostre de 2026 até 2023", []) == [
        2023,
        2024,
        2025,
        2026,
    ]


def test_value_sort_direction_recognizes_user_phrasings() -> None:
    assert _value_sort_direction("Coloque em ordem crescente") == "ascending"
    assert _value_sort_direction("Mostre do menor para o maior") == "ascending"
    assert _value_sort_direction("Coloque em ordem decrescente") == "descending"
    assert _value_sort_direction("Mostre do maior para o menor") == "descending"
    assert _value_sort_direction("Mostre por ano") is None


def test_historical_search_sorts_values_and_preserves_source_links() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for index, (year, code, value) in enumerate(
            [(2019, "20201", "1.000"), (2020, "22201", "2.000")], start=1
        ):
            document = Document(
                year=year,
                title=f"LOA {year}",
                kind=DocumentKind.VOLUME,
                official_url=None,
            )
            version = DocumentVersion(
                document=document,
                filename=f"range-{year}.pdf",
                sha256=str(index + 6) * 64,
                byte_size=100,
                page_count=1,
            )
            page = Page(
                version=version,
                pdf_page_number=10,
                printed_page_label="9",
                original_text=f"{code} INCRA {value}",
                page_sha256=str(index + 8) * 64,
            )
            db.add_all([document, version, page])
            db.flush()
            db.add(
                make_record(
                    year=year,
                    document_version_id=version.id,
                    page_id=page.id,
                    organization_code=code,
                    organization_name="INCRA",
                    parent_organization_code="agricultura_desenvolvimento_agrario_pesca",
                    original_value=value,
                    numeric_value=Decimal(value.replace(".", "")),
                    source_text=page.original_text,
                    deduplication_key=str(index + 10) * 64,
                )
            )
        db.flush()
        seed_editorial_map(db)
        backfill_budget_record_classification(db)
        db.commit()

        descending = search_documents(
            db,
            SearchRequest(
                query="Mostre a série documental do INCRA de 2019 a 2020 em ordem decrescente",
                interpretation_confirmed=True,
            ),
        )
        expanded = search_documents(
            db,
            SearchRequest(
                query="Mostre a série documental do INCRA de 2019 a 2022",
                interpretation_confirmed=True,
            ),
        )

    assert descending.summary.index("2020 (código 22201)") < descending.summary.index(
        "2019 (código 20201)"
    )
    assert [source.year for source in descending.sources] == [2020, 2019]
    assert descending.sources[0].excerpt == "22201 INCRA 2.000"
    assert expanded.insufficient_evidence
    assert any("2021, 2022" in limitation for limitation in expanded.limitations)
