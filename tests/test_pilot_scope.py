from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from loa_api.config import Settings
from loa_api.database import Base
from loa_api.models import BudgetRecord
from loa_api.schemas import SearchRequest
from loa_api.search import pilot_comparison_allowed, pilot_out_of_scope, pilot_query_allowed


ALLOWED = {"educacao", "fiscal_74000"}


def record(code: str, name: str, area: str, key: str) -> BudgetRecord:
    return BudgetRecord(
        year=2024,
        document_version_id=1,
        page_id=1,
        organization_code=code,
        organization_name=name,
        parent_organization_code="74000" if area != "educacao" else "26000",
        area_slug=area,
        record_level="subtotal_unidade",
        evidence_status="homologated",
        aggregation_policy="component",
        original_value="100",
        numeric_value=Decimal("100"),
        unit="R$ 1,00",
        source_text="evidência",
        deduplication_key=key * 64,
    )


def seeded_session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add_all(
        [
            record("26298", "Fundo Nacional de Desenvolvimento da Educação", "educacao", "a"),
            record("74901", "Recursos sob Supervisão do Fundo de Financiamento ao Estudante", "fiscal_74000", "b"),
            record("74202", "Recursos sob Supervisão do Fundo Nacional de Saúde", "saude", "c"),
            record("52101", "Ministério da Defesa", "defesa", "d"),
        ]
    )
    db.commit()
    return db


def test_default_settings_release_all_homologated_areas() -> None:
    settings = Settings(_env_file=None)
    assert not settings.pilot_education_only
    assert settings.allowed_pilot_areas == set()


def test_education_and_74000_queries_are_allowed() -> None:
    with seeded_session() as db:
        assert pilot_query_allowed(db, "Qual o orçamento do FNDE?", ALLOWED)
        assert pilot_query_allowed(
            db, "Qual o total de Operações Oficiais de Crédito em 2024?", ALLOWED
        )
        assert pilot_query_allowed(db, "Mostre a unidade 74901", ALLOWED)


def test_other_areas_and_protected_74000_codes_remain_blocked() -> None:
    with seeded_session() as db:
        assert not pilot_query_allowed(db, "Qual o orçamento da Defesa?", ALLOWED)
        assert not pilot_query_allowed(db, "Qual o orçamento da Saúde?", ALLOWED)
        assert not pilot_query_allowed(db, "Mostre a unidade 74202", ALLOWED)


def test_out_of_scope_response_names_released_scope() -> None:
    response = pilot_out_of_scope(
        SearchRequest(query="Qual o orçamento da Defesa?"), ALLOWED
    )
    assert response.insufficient_evidence
    assert "Educação" in response.summary
    assert "Operações Oficiais de Crédito (74000)" in response.summary
    assert "demais áreas permanecem bloqueadas" in response.limitations[0]


def test_comparison_allowlist_applies_to_every_structured_level() -> None:
    with seeded_session() as db:
        education_program = record("26000", "Educação", "educacao", "e")
        education_program.organization_code = None
        education_program.program_code = "5011"
        defense_program = record("52000", "Defesa", "defesa", "f")
        defense_program.organization_code = None
        defense_program.program_code = "6112"
        db.add_all([education_program, defense_program])
        db.commit()

        assert pilot_comparison_allowed(db, "organization", "74901", ALLOWED)
        assert not pilot_comparison_allowed(db, "organization", "74202", ALLOWED)
        assert pilot_comparison_allowed(db, "program", "5011", ALLOWED)
        assert not pilot_comparison_allowed(db, "program", "6112", ALLOWED)
        assert not pilot_comparison_allowed(db, "action", "inexistente", ALLOWED)
