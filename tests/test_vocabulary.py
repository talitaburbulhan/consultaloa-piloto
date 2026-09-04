from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from loa_api.database import Base
from loa_api.models import BudgetRecord, Document, DocumentKind, DocumentVersion, Page
from loa_api.schemas import SearchRequest
from loa_api.search import search_documents
from loa_api.vocabulary import interpret_query


def test_everyday_bolsa_familia_question_is_normalized() -> None:
    result = interpret_query("Em que ano o Bolsa Família recebeu mais dinheiro?")
    assert result["intent"] == "compare_maximum"
    assert result["entity"] == "bolsa_familia"
    assert result["technical_concept"] == "dotacao_autorizada"
    assert "maior valor" in result["normalized_query"]


def test_revenue_word_for_program_requires_confirmation() -> None:
    result = interpret_query("Em que ano houve mais receita pro Bolsa Família?")
    assert result["requires_confirmation"]
    assert "entrada de recursos" in result["confirmation_reason"]


def test_ambiguous_query_stops_before_document_search() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        response = search_documents(
            db,
            SearchRequest(query="Em que ano houve mais receita pro Bolsa Família?"),
        )
    assert response.interpretation.requires_confirmation
    assert response.evidence == []
    assert "Confirme" in response.summary


def test_execution_language_is_outside_corpus() -> None:
    result = interpret_query("Quanto foi pago pelo Bolsa Família?")
    assert result["intent"] == "execution"
    assert not result["available_in_corpus"]


def test_missing_article_still_recognizes_budget_question() -> None:
    result = interpret_query("Qual foi orçamento do Ministério da Educação?")
    assert result["intent"] == "authorized_amount"
    assert result["entity"] == "ministerio_educacao"


def test_value_authorized_wording_is_a_budget_question() -> None:
    result = interpret_query("Qual foi o valor autorizado na LOA para Cultura?")

    assert result["intent"] == "authorized_amount"
    assert result["entity"] == "cultura"
    assert result["requires_structured_values"]


def test_minc_is_ministry_of_culture_and_never_mec() -> None:
    result = interpret_query("Qual foi o orçamento do MinC em 2023?")

    assert result["intent"] == "authorized_amount"
    assert result["entity"] == "ministerio_cultura"
    assert result["entity_label"] == "Ministério da Cultura"
    assert not result["requires_confirmation"]


def test_minc_2023_does_not_fall_back_to_mec_or_program_value() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        response = search_documents(
            db,
            SearchRequest(
                query="Qual foi o orçamento do MinC em 2023?",
                years=list(range(2019, 2027)),
            ),
        )

    assert "Não há um total exclusivo e homologado do Ministério da Cultura" in response.summary
    assert "para 2023" in response.summary
    assert "para 2019" not in response.summary
    assert "Ministério do Turismo em 2021–2023" in response.summary
    assert "Ministério da Educação" not in response.summary
    assert response.insufficient_evidence
    assert response.sources == []


def test_colloquial_fnde_names_are_recognized() -> None:
    queries = [
        "Qual foi o orçamento do Fundo Nacional da Educação?",
        "Quanto recebeu o fundo nacional de educação?",
        "Orçamento do fundo da educação",
    ]

    for query in queries:
        result = interpret_query(query)
        assert result["entity"] == "fnde"
        assert result["entity_label"] == "Fundo Nacional de Desenvolvimento da Educação"


def test_count_institutions_wording_is_recognized() -> None:
    result = interpret_query("Quantas instituições tem no orçamento a Educação?")

    assert result["intent"] == "count_institutions"
    assert result["entity"] == "educacao"


def test_count_mec_units_natural_wordings_are_recognized() -> None:
    queries = [
        "Existem quantas unidades vinculadas ao MEC?",
        "Quantas unidades do MEC existem?",
        "Qual o número de unidades vinculadas ao órgão 26000?",
        "Informe a quantidade de unidades do MEC",
    ]

    for query in queries:
        result = interpret_query(query)
        assert result["intent"] == "count_institutions"
        assert result["entity"] == "ministerio_educacao"


def test_list_institutions_wording_is_recognized() -> None:
    result = interpret_query(
        "Quais são as 40 unidades orçamentárias classificadas como Institutos Federais?"
    )

    assert result["intent"] == "list_institutions"
    assert result["entity"] == "institutos_federais"


def test_direct_university_list_wordings_are_recognized() -> None:
    queries = [
        "Quais são as universidades federais?",
        "Quais universidades federais estão na LOA?",
        "Liste as universidades federais",
        "Mostre as universidades federais",
    ]

    for query in queries:
        result = interpret_query(query)
        assert result["intent"] == "list_institutions"
        assert result["entity"] == "universidades_federais"


def test_direct_institute_list_wordings_are_recognized() -> None:
    queries = [
        "Quais são os institutos federais?",
        "Quais institutos federais estão na LOA?",
        "Liste os institutos federais",
        "Mostre os institutos federais",
    ]

    for query in queries:
        result = interpret_query(query)
        assert result["intent"] == "list_institutions"
        assert result["entity"] == "institutos_federais"


def test_category_member_ranking_wording_is_recognized() -> None:
    result = interpret_query("Qual é o instituto federal com maior orçamento?")

    assert result["intent"] == "compare_maximum"
    assert result["entity"] == "institutos_federais"


def test_explicit_ranking_wordings_are_recognized() -> None:
    queries = [
        "Qual é o ranking de orçamento das universidades federais?",
        "Mostre o ranking de orçamento das universidades federais",
        "Ordene as universidades federais por orçamento",
    ]

    for query in queries:
        result = interpret_query(query)
        assert result["intent"] == "compare_maximum"
        assert result["entity"] == "universidades_federais"


def test_mec_institution_ranking_wordings_are_recognized() -> None:
    queries = [
        "Qual o ranking de orçamento das instituições do MEC?",
        "Qual o ranking de orçamento das intituições do MEC?",
        "Ordene as unidades do MEC por orçamento",
    ]

    for query in queries:
        result = interpret_query(query)
        assert result["intent"] == "compare_maximum"
        assert result["entity"] in {"educacao", "ministerio_educacao"}


def test_unqualified_university_means_federal_university_in_corpus() -> None:
    queries = [
        "Qual foi a universidade com maior orçamento?",
        "Liste as universidades",
        "Compare o orçamento das universidades",
    ]

    for query in queries:
        result = interpret_query(query)
        assert result["entity"] == "universidades_federais"
        assert result["entity_label"] == "Universidades federais"


def test_budget_listing_by_category_wordings_are_recognized() -> None:
    queries = [
        "Liste o orçamento das universidades federais em 2022",
        "Mostre o orçamento das universidades em 2022",
        "Liste os orçamentos dos institutos federais",
    ]

    for query in queries:
        result = interpret_query(query)
        assert result["intent"] == "list_institutions"
        assert result["entity"] in {
            "universidades_federais",
            "institutos_federais",
        }


def test_institute_feedback_queries_return_individual_values_without_group_sum() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        document = Document(
            year=2022,
            title="LOA 2022",
            kind=DocumentKind.LOA,
            official_url=None,
        )
        version = DocumentVersion(
            document=document,
            filename="2022_volume4.pdf",
            sha256="e" * 64,
            byte_size=100,
            page_count=2,
        )
        baiano_page = Page(
            version=version,
            pdf_page_number=10,
            printed_page_label="6",
            original_text="26404 Instituto Federal Baiano Total 500.000.000",
            page_sha256="f" * 64,
        )
        other_page = Page(
            version=version,
            pdf_page_number=11,
            printed_page_label="7",
            original_text="26408 Instituto Federal do Maranhão Total 700.000.000",
            page_sha256="1" * 64,
        )
        db.add_all([document, version, baiano_page, other_page])
        db.flush()
        db.add_all(
            [
                BudgetRecord(
                    year=2022,
                    document_version_id=version.id,
                    page_id=baiano_page.id,
                    organization_code="26404",
                    organization_name="Instituto Federal Baiano",
                    institution_category="educacao_profissional",
                    parent_organization_code="26000",
                    original_value="500.000.000",
                    numeric_value=500000000,
                    unit="R$ 1,00",
                    source_text=baiano_page.original_text,
                    deduplication_key="2" * 64,
                ),
                BudgetRecord(
                    year=2022,
                    document_version_id=version.id,
                    page_id=other_page.id,
                    organization_code="26408",
                    organization_name="Instituto Federal do Maranhão",
                    institution_category="educacao_profissional",
                    parent_organization_code="26000",
                    original_value="700.000.000",
                    numeric_value=700000000,
                    unit="R$ 1,00",
                    source_text=other_page.original_text,
                    deduplication_key="3" * 64,
                ),
            ]
        )
        db.commit()

        collective = search_documents(
            db,
            SearchRequest(
                query="Mostre os orçamentos de cada um dos institutos federais em 2022 em ordem crescente",
                interpretation_confirmed=True,
            ),
        )
        individual = search_documents(
            db,
            SearchRequest(
                query="Qual foi o orçamento do Instituto Federal Baiano em 2022?",
                interpretation_confirmed=True,
            ),
        )

    assert len(collective.listed_units) == 2
    assert {item.original_value for item in collective.listed_units} == {
        "500.000.000",
        "700.000.000",
    }
    assert [item.code for item in collective.listed_units] == ["26404", "26408"]
    assert "Instituto Federal Baiano" in individual.summary
    assert "R$ 500.000.000" in individual.summary
    assert "1.200.000.000" not in individual.summary
    assert len(individual.sources) == 1


def test_specific_unit_names_do_not_match_prefixes_or_parent_institutions() -> None:
    from loa_api.chunking import normalize
    from loa_api.search import _alias_spans, _drop_nested_institution_matches

    parana_query = normalize("orçamento da Universidade Federal do Paraná")
    assert _alias_spans("universidade federal do parana", parana_query)
    assert not _alias_spans("universidade federal do para", parana_query)

    hospital_query = normalize(
        "orçamento do Hospital de Clínicas da Universidade Federal do Paraná"
    )
    university_span = _alias_spans(
        "universidade federal do parana", hospital_query
    )
    hospital_span = _alias_spans(
        "hospital de clinicas da universidade federal do parana", hospital_query
    )
    candidates = {
        "26241": ("Universidade Federal do Paraná", []),
        "26372": ("Hospital de Clínicas da Universidade Federal do Paraná", []),
    }
    _drop_nested_institution_matches(
        candidates,
        {"26241": university_span, "26372": hospital_span},
    )
    assert set(candidates) == {"26372"}

    # Nomes iguais com códigos históricos ocupam o mesmo trecho e permanecem
    # disponíveis para que o exercício selecione o segmento documental correto.
    historical = {
        "20201": ("INCRA", []),
        "22201": ("INCRA", []),
    }
    same_span = _alias_spans("incra", normalize("orçamento do INCRA"))
    _drop_nested_institution_matches(
        historical,
        {"20201": same_span, "22201": same_span},
    )
    assert set(historical) == {"20201", "22201"}


def test_identical_unit_names_in_same_year_require_code_instead_of_sum() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        document = Document(
            year=2024,
            title="LOA 2024",
            kind=DocumentKind.LOA,
            official_url=None,
        )
        version = DocumentVersion(
            document=document,
            filename="2024_volume4.pdf",
            sha256="4" * 64,
            byte_size=100,
            page_count=2,
        )
        pages = [
            Page(
                version=version,
                pdf_page_number=index,
                printed_page_label=str(index),
                original_text=f"{code} Recursos sob Supervisão do Ministério da Fazenda",
                page_sha256=str(index) * 64,
            )
            for index, code in ((1, "71101"), (2, "73101"))
        ]
        db.add_all([document, version, *pages])
        db.flush()
        for index, (page, code, area, value) in enumerate(
            zip(
                pages,
                ("71101", "73101"),
                ("fiscal_71000", "fiscal_73000"),
                (100, 200),
            ),
            start=1,
        ):
            db.add(
                BudgetRecord(
                    year=2024,
                    document_version_id=version.id,
                    page_id=page.id,
                    organization_code=code,
                    organization_name="Recursos sob Supervisão do Ministério da Fazenda",
                    area_slug=area,
                    evidence_status="homologated",
                    original_value=str(value),
                    numeric_value=value,
                    unit="R$ 1,00",
                    source_text=page.original_text,
                    deduplication_key=str(index + 5) * 64,
                )
            )
        db.commit()
        ambiguous = search_documents(
            db,
            SearchRequest(
                query="Qual foi o orçamento dos Recursos sob Supervisão do Ministério da Fazenda em 2024?",
                interpretation_confirmed=True,
            ),
        )
        explicit = search_documents(
            db,
            SearchRequest(
                query="Qual foi o orçamento da unidade 71101 em 2024?",
                interpretation_confirmed=True,
            ),
        )

    assert ambiguous.insufficient_evidence
    assert "Escolha pelo contexto" in ambiguous.summary
    assert "Não é necessário conhecer o código" in ambiguous.summary
    assert "Encargos Financeiros da União" in ambiguous.summary
    assert "Transferências a Estados" in ambiguous.summary
    assert ambiguous.sources == []
    assert "não foram somadas" in ambiguous.limitations[0]
    assert "R$ 100" in explicit.summary
    assert "R$ 200" not in explicit.summary


def test_area_context_disambiguates_identical_unit_names_without_code() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        document = Document(
            year=2024, title="LOA 2024", kind=DocumentKind.LOA, official_url=None
        )
        version = DocumentVersion(
            document=document,
            filename="2024_volume4.pdf",
            sha256="a" * 64,
            byte_size=100,
            page_count=2,
        )
        for index, (code, area, value) in enumerate(
            (("71101", "fiscal_71000", 100), ("74102", "fiscal_74000", 300)),
            start=1,
        ):
            page = Page(
                version=version,
                pdf_page_number=index,
                printed_page_label=str(index),
                original_text=f"{code} Recursos sob Supervisão do Ministério da Fazenda",
                page_sha256=str(index + 6) * 64,
            )
            db.add(page)
            db.flush()
            db.add(
                BudgetRecord(
                    year=2024,
                    document_version_id=version.id,
                    page_id=page.id,
                    organization_code=code,
                    organization_name="Recursos sob Supervisão do Ministério da Fazenda",
                    area_slug=area,
                    evidence_status="homologated",
                    original_value=str(value),
                    numeric_value=value,
                    unit="R$ 1,00",
                    source_text=page.original_text,
                    deduplication_key=str(index + 7) * 64,
                )
            )
        db.commit()
        response = search_documents(
            db,
            SearchRequest(
                query=(
                    "Qual foi o orçamento dos Recursos sob Supervisão do Ministério "
                    "da Fazenda em Operações Oficiais de Crédito em 2024?"
                ),
                interpretation_confirmed=True,
            ),
        )

    assert "código 74102" in response.summary
    assert "R$ 300" in response.summary
    assert "R$ 100" not in response.summary


def test_health_unit_group_wordings_are_recognized() -> None:
    expected = [
        ("Quantas unidades vinculadas ao Ministério da Saúde existem?", "count_institutions"),
        ("Quais são as unidades vinculadas ao Ministério da Saúde?", "list_institutions"),
        ("Qual unidade da saúde teve maior orçamento em 2022?", "compare_maximum"),
    ]

    for query, intent in expected:
        result = interpret_query(query)
        assert result["intent"] == intent
        assert result["entity"] == "unidades_saude"


def test_small_typos_still_recognize_entity_and_intent() -> None:
    result = interpret_query("Qual o orcamnto do ministerio da educaçao?")
    assert result["intent"] == "authorized_amount"
    assert result["entity"] == "ministerio_educacao"


def test_structured_program_value_is_returned_with_source() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        document = Document(
            year=2026,
            title="LOA 2026",
            kind=DocumentKind.LOA,
            official_url=None,
        )
        version = DocumentVersion(
            document=document,
            filename="2026.pdf",
            sha256="a" * 64,
            byte_size=100,
            page_count=1,
        )
        page = Page(
            version=version,
            pdf_page_number=1,
            printed_page_label="1",
            original_text="Programa 5128 Bolsa Família R$ 159.534.436.668",
            page_sha256="b" * 64,
        )
        db.add_all([document, version, page])
        db.flush()
        db.add(
            BudgetRecord(
                year=2026,
                document_version_id=version.id,
                page_id=page.id,
                program_code="5128",
                original_value="159.534.436.668",
                numeric_value=159534436668,
                unit="R$ 1,00",
                source_text=page.original_text,
                deduplication_key="c" * 64,
            )
        )
        db.commit()
        response = search_documents(
            db,
            SearchRequest(
                query="Quanto foi destinado ao Bolsa Família em 2026?",
                interpretation_confirmed=True,
            ),
        )
    assert "R$ 159.534.436.668" in response.summary
    assert response.sources[0].pdf_page == 1
    assert response.sources[0].excerpt == "Programa 5128 Bolsa Família R$ 159.534.436.668"


def test_structured_culture_value_is_returned_with_source() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        document = Document(
            year=2026,
            title="LOA 2026",
            kind=DocumentKind.LOA,
            official_url=None,
        )
        version = DocumentVersion(
            document=document,
            filename="2026-cultura.pdf",
            sha256="d" * 64,
            byte_size=100,
            page_count=1,
        )
        page = Page(
            version=version,
            pdf_page_number=1,
            printed_page_label="1",
            original_text="Programa 5125 Direito à Cultura R$ 2.419.370.078",
            page_sha256="e" * 64,
        )
        db.add_all([document, version, page])
        db.flush()
        db.add(
            BudgetRecord(
                year=2026,
                document_version_id=version.id,
                page_id=page.id,
                program_code="5125",
                original_value="2.419.370.078",
                numeric_value=2419370078,
                unit="R$ 1,00",
                source_text=page.original_text,
                deduplication_key="f" * 64,
            )
        )
        db.commit()
        response = search_documents(
            db,
            SearchRequest(
                query="Quanto foi destinado à Cultura em 2026?",
                interpretation_confirmed=True,
            ),
        )
    assert "R$ 2.419.370.078" in response.summary
    assert response.sources[0].pdf_page == 1


def test_program_code_is_distinguished_from_budget_year() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        document = Document(
            year=2019,
            title="LOA 2019",
            kind=DocumentKind.LOA,
            official_url=None,
        )
        version = DocumentVersion(
            document=document,
            filename="2019-volume2.pdf",
            sha256="1" * 64,
            byte_size=100,
            page_count=20,
        )
        page = Page(
            version=version,
            pdf_page_number=14,
            printed_page_label="9",
            original_text="Programa 2021 Ciência, Tecnologia e Inovação",
            page_sha256="2" * 64,
        )
        db.add_all([document, version, page])
        db.flush()
        db.add(
            BudgetRecord(
                year=2019,
                document_version_id=version.id,
                page_id=page.id,
                program_code="2021",
                original_value="2.620.396.435",
                numeric_value=2620396435,
                unit="R$ 1,00",
                source_text=(
                    "Programa:2021 Ciência, Tecnologia e Inovação "
                    "Valor do Programa Constante da LOA: 2.620.396.435"
                ),
                deduplication_key="3" * 64,
            )
        )
        db.commit()
        response = search_documents(
            db,
            SearchRequest(
                query="Qual foi o orçamento do programa 2021 no ano de 2019?",
                interpretation_confirmed=True,
            ),
        )
    assert "R$ 2.620.396.435" in response.summary
    assert response.sources[0].pdf_page == 14


def test_university_acronym_resolves_to_organization_code() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        document = Document(
            year=2022,
            title="LOA 2022",
            kind=DocumentKind.LOA,
            official_url=None,
        )
        version = DocumentVersion(
            document=document,
            filename="2022-volume1.pdf",
            sha256="4" * 64,
            byte_size=100,
            page_count=200,
        )
        page = Page(
            version=version,
            pdf_page_number=171,
            printed_page_label="167",
            original_text="26246 Universidade Federal de Santa Catarina",
            page_sha256="5" * 64,
        )
        db.add_all([document, version, page])
        db.flush()
        db.add(
            BudgetRecord(
                year=2022,
                document_version_id=version.id,
                page_id=page.id,
                organization_code="26246",
                organization_name="Universidade Federal de Santa Catarina",
                institution_category="universidade",
                parent_organization_code="26000",
                original_value="1.678.428.188",
                numeric_value=1678428188,
                unit="R$ 1,00",
                source_text=(
                    "Unidade universitária federal: 26246 "
                    "Universidade Federal de Santa Catarina "
                    "Total autorizado na LOA: 1.678.428.188"
                ),
                deduplication_key="6" * 64,
            )
        )
        page_ufba = Page(
            version=version,
            pdf_page_number=172,
            printed_page_label="168",
            original_text="26232 Universidade Federal da Bahia",
            page_sha256="a" * 64,
        )
        db.add(page_ufba)
        db.flush()
        db.add(
            BudgetRecord(
                year=2022,
                document_version_id=version.id,
                page_id=page_ufba.id,
                organization_code="26232",
                organization_name="Universidade Federal da Bahia",
                institution_category="universidade",
                parent_organization_code="26000",
                original_value="1.686.119.542",
                numeric_value=1686119542,
                unit="R$ 1,00",
                source_text=(
                    "Unidade universitária federal: 26232 "
                    "Universidade Federal da Bahia "
                    "Total autorizado na LOA: 1.686.119.542"
                ),
                deduplication_key="b" * 64,
            )
        )
        page_ifsc = Page(
            version=version,
            pdf_page_number=173,
            printed_page_label="169",
            original_text="26438 Instituto Federal de Santa Catarina",
            page_sha256="c" * 64,
        )
        db.add(page_ifsc)
        db.flush()
        db.add(
            BudgetRecord(
                year=2022,
                document_version_id=version.id,
                page_id=page_ifsc.id,
                organization_code="26438",
                organization_name="Instituto Federal de Santa Catarina",
                institution_category="educacao_profissional",
                parent_organization_code="26000",
                original_value="1.000.000.000",
                numeric_value=1000000000,
                unit="R$ 1,00",
                source_text=(
                    "Unidade vinculada ao MEC: 26438 Instituto Federal de Santa Catarina. "
                    "Total autorizado na LOA: 1.000.000.000"
                ),
                deduplication_key="d" * 64,
            )
        )
        document_2021 = Document(
            year=2021,
            title="LOA 2021",
            kind=DocumentKind.LOA,
            official_url=None,
        )
        version_2021 = DocumentVersion(
            document=document_2021,
            filename="2021-volume1.pdf",
            sha256="7" * 64,
            byte_size=100,
            page_count=200,
        )
        page_2021 = Page(
            version=version_2021,
            pdf_page_number=171,
            printed_page_label="167",
            original_text="26246 Universidade Federal de Santa Catarina",
            page_sha256="8" * 64,
        )
        db.add_all([document_2021, version_2021, page_2021])
        db.flush()
        db.add(
            BudgetRecord(
                year=2021,
                document_version_id=version_2021.id,
                page_id=page_2021.id,
                organization_code="26246",
                organization_name="Universidade Federal de Santa Catarina",
                institution_category="universidade",
                parent_organization_code="26000",
                original_value="1.500.000.000",
                numeric_value=1500000000,
                unit="R$ 1,00",
                source_text=(
                    "Unidade universitária federal: 26246 "
                    "Universidade Federal de Santa Catarina "
                    "Total autorizado na LOA: 1.500.000.000"
                ),
                deduplication_key="9" * 64,
            )
        )
        db.commit()
        response = search_documents(
            db,
            SearchRequest(
                query="Quanto foi o orçamento da UFSC em 2022?",
                interpretation_confirmed=True,
            ),
        )
        partial_response = search_documents(
            db,
            SearchRequest(
                query="Qual foi o orçamento da UFSC e da USP em 2022?",
                interpretation_confirmed=True,
            ),
        )
        missing_response = search_documents(
            db,
            SearchRequest(
                query="Qual foi o orçamento da USP em 2022?",
                interpretation_confirmed=True,
            ),
        )
        multi_year_response = search_documents(
            db,
            SearchRequest(
                query="Compare o orçamento da UFSC.",
                years=[2021, 2022],
                interpretation_confirmed=True,
            ),
        )
        multi_institution_response = search_documents(
            db,
            SearchRequest(
                query="Qual foi o orçamento da UFSC e da UFBA?",
                years=[2022],
                interpretation_confirmed=True,
            ),
        )
        full_period_response = search_documents(
            db,
            SearchRequest(
                query="Qual foi o orçamento da UFSC?",
                interpretation_confirmed=True,
            ),
        )
        largest_university_response = search_documents(
            db,
            SearchRequest(
                query="Qual foi a universidade federal que teve o maior orçamento?",
                years=[2022],
                interpretation_confirmed=True,
            ),
        )
        education_count_response = search_documents(
            db,
            SearchRequest(
                query="Quantas instituições tem no orçamento da educação?",
                years=[2022],
                interpretation_confirmed=True,
            ),
        )
        education_ranking_response = search_documents(
            db,
            SearchRequest(
                query="Qual instituição da educação teve o maior orçamento em 2022?",
                interpretation_confirmed=True,
            ),
        )
        institutes_response = search_documents(
            db,
            SearchRequest(
                query="Quanto foi destinado aos Institutos Federais em 2022?",
                interpretation_confirmed=True,
            ),
        )
    assert "R$ 1.678.428.188" in response.summary
    assert "código 26246" in response.summary
    assert "R$ 1.678.428.188" in partial_response.summary
    assert "Não encontrei USP" in partial_response.summary
    assert "comparação solicitada não foi realizada" in partial_response.summary
    assert "Não encontrei USP" in missing_response.summary
    assert missing_response.insufficient_evidence
    assert "R$ 1.500.000.000" in multi_year_response.summary
    assert "R$ 1.678.428.188" in multi_year_response.summary
    assert [source.year for source in multi_year_response.sources] == [2021, 2022]
    assert "R$ 1.678.428.188" in multi_institution_response.summary
    assert "R$ 1.686.119.542" in multi_institution_response.summary
    assert len(multi_institution_response.sources) == 2
    assert "R$ 1.500.000.000" in full_period_response.summary
    assert "R$ 1.678.428.188" in full_period_response.summary
    assert [source.year for source in full_period_response.sources] == [2021, 2022]
    assert "2019, 2020, 2023, 2024, 2025, 2026" in full_period_response.summary
    assert "Universidade Federal da Bahia" in largest_university_response.summary
    assert "R$ 1.686.119.542" in largest_university_response.summary
    assert len(largest_university_response.sources) == 1
    assert "2022: 3 unidades vinculadas ao MEC" in education_count_response.summary
    assert "Universidade Federal da Bahia" in education_ranking_response.summary
    assert "R$ 1.686.119.542" in education_ranking_response.summary
    assert "2022: R$ 1.000.000.000" in institutes_response.summary
