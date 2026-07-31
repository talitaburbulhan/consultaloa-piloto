import json
import re

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from .chunking import cosine, embed, normalize
from .editorial import INSUFFICIENT_EVIDENCE, ambiguity_warnings, is_execution_query
from .models import BudgetRecord, Chunk, Document, DocumentVersion, Page
from .schemas import (
    Evidence,
    ListedUnit,
    QueryInterpretation,
    SearchRequest,
    SearchResponse,
    SourceReference,
)
from .vocabulary import interpret_query


def _terms(query: str) -> list[str]:
    return [term for term in re.findall(r"[\wÀ-ÿ-]+", query.casefold()) if len(term) >= 3][:12]


STRUCTURED_PROGRAM_CODES = {
    "fnde": {
        2019: "26298",
        2020: "26298",
        2021: "26298",
        2022: "26298",
        2023: "26298",
        2024: "26298",
        2025: "26298",
        2026: "26298",
    },
    "ministerio_educacao": {
        2019: "26000",
        2020: "26000",
        2021: "26000",
        2022: "26000",
        2023: "26000",
        2024: "26000",
        2025: "26000",
        2026: "26000",
    },
    "educacao": {
        2019: "26000",
        2020: "26000",
        2021: "26000",
        2022: "26000",
        2023: "26000",
        2024: "26000",
        2025: "26000",
        2026: "26000",
    },
    "bolsa_familia": {
        2019: "2019",
        2020: "5028",
        2021: "5028",
        2022: "5028",
        2023: "5035",
        2024: "5128",
        2025: "5128",
        2026: "5128",
    },
    "cultura": {
        2019: "2027",
        2020: "5025",
        2021: "5025",
        2022: "5025",
        2023: "5025",
        2024: "5125",
        2025: "5125",
        2026: "5125",
    },
    "defesa": {
        2019: "2058",
        2020: "6012",
        2021: "6012",
        2022: "6012",
        2023: "6012",
        2024: "6112",
        2025: "6112",
        2026: "6112",
    },
    "educacao_superior": {
        2020: "5013",
        2021: "5013",
        2022: "5013",
        2023: "5013",
        2024: "5113",
        2025: "5113",
        2026: "5113",
    },
    "educacao_profissional": {
        2020: "5012",
        2021: "5012",
        2022: "5012",
        2023: "5012",
        2024: "5112",
        2025: "5112",
        2026: "5112",
    },
    "educacao_basica": {
        2020: "5011",
        2021: "5011",
        2022: "5011",
        2023: "5011",
        2024: "5111",
        2025: "5111",
        2026: "5111",
    },
    "frgps": {
        2019: "55902",
        2020: "25917",
        2021: "25917",
        2022: "40904",
        2023: "40904",
        2024: "33904",
        2025: "33904",
        2026: "33904",
    },
    "inss": {
        2019: "55201",
        2020: "25303",
        2021: "25303",
        2022: "40201",
        2023: "40201",
        2024: "33201",
        2025: "33201",
        2026: "33201",
    },
    "previc": {
        2019: "25206",
        2020: "25206",
        2021: "25206",
        2022: "40206",
        2023: "40206",
        2024: "33206",
        2025: "33206",
        2026: "33206",
    },
    "fnas": {
        2019: "55901",
        2020: "55901",
        2021: "55901",
        2022: "55901",
        2023: "55901",
        2024: "55901",
        2025: "55901",
        2026: "55901",
    },
}

STRUCTURED_SOURCE_FILES = {
    "defesa": {
        2019: "2019_volume2.pdf",
        2020: "2020_volume2.pdf",
        2021: "2021_volume2.pdf",
        2022: "2022_volume1.pdf",
        2023: "2023_volume2.pdf",
        2024: "2024_volume2.pdf",
        2025: "2025_volume2.pdf",
        2026: "2026_volume2.pdf",
    }
}

STRUCTURED_ENTITY_FIELDS = {
    "educacao": "organization_code",
    "fnde": "organization_code",
    "ministerio_educacao": "organization_code",
    "frgps": "organization_code",
    "inss": "organization_code",
    "previc": "organization_code",
    "fnas": "organization_code",
}

STRUCTURED_MISSING_YEARS = {}

INSTITUTION_GROUPS = {
    "educacao": {
        "parent_organization_code": "26000",
        "institution_category": None,
        "label": "unidades vinculadas ao MEC",
    },
    "ministerio_educacao": {
        "parent_organization_code": "26000",
        "institution_category": None,
        "label": "unidades vinculadas ao MEC",
    },
    "universidades_federais": {
        "parent_organization_code": "26000",
        "institution_category": "universidade",
        "label": "universidades federais",
    },
    "institutos_federais": {
        "parent_organization_code": "26000",
        "institution_category": "educacao_profissional",
        "label": "unidades de educação profissional",
    },
    "seguridade_social": {
        "parent_organization_code": "seguridade_social",
        "institution_category": None,
        "label": "instituições da Seguridade Social",
        "deduplicate_by_name": True,
    },
    "unidades_saude": {
        "parent_organization_code": "36000",
        "institution_category": None,
        "label": "unidades vinculadas ao Ministério da Saúde",
    },
}

CATEGORY_MEMBER_RANKINGS = {
    "educacao": {
        "parent_organization_code": "26000",
        "institution_category": None,
        "label": "unidades vinculadas ao MEC",
        "member_terms": ("instituicao", "unidade", "orgao"),
        "limitations": [
            "O ranking inclui as unidades orçamentárias vinculadas ao MEC presentes e validadas no acervo."
        ],
    },
    "ministerio_educacao": {
        "parent_organization_code": "26000",
        "institution_category": None,
        "label": "unidades vinculadas ao MEC",
        "member_terms": ("instituicao", "unidade", "orgao"),
        "limitations": [
            "A expressão “instituições do MEC” é interpretada como unidades orçamentárias vinculadas ao Ministério da Educação."
        ],
    },
    "universidades_federais": {
        "parent_organization_code": "26000",
        "institution_category": "universidade",
        "label": "universidades federais",
        "member_terms": ("universidade", "unidade"),
        "limitations": [
            "Nesta aplicação, “universidade” sem outro qualificador significa universidade federal presente no acervo das LOAs da União."
        ],
    },
    "institutos_federais": {
        "parent_organization_code": "26000",
        "institution_category": "educacao_profissional",
        "label": "unidades de educação profissional",
        "member_terms": ("instituto", "unidade"),
        "limitations": [
            "A categoria inclui 38 Institutos Federais e dois Cefets, todos comparados como unidades de educação profissional."
        ],
    },
    "seguridade_social": {
        "parent_organization_code": "seguridade_social",
        "institution_category": None,
        "label": "instituições da Seguridade Social",
        "member_terms": ("instituicao", "unidade", "orgao", "fundo", "autarquia"),
        "limitations": [
            "O ranking inclui somente instituições da Seguridade Social já reconciliadas e validadas no acervo.",
            "Mudanças de código da mesma instituição entre exercícios são tratadas como continuidade da série.",
        ],
    },
    "unidades_saude": {
        "parent_organization_code": "36000",
        "institution_category": None,
        "label": "unidades vinculadas ao Ministério da Saúde",
        "member_terms": ("unidade", "instituicao", "orgao"),
        "limitations": [
            "O ranking cobre as seis unidades do Quadro 5 vinculadas ao Ministério da Saúde em cada exercício."
        ],
    },
}


def _official_budget_url(year: int, document_url: str | None = None) -> str:
    return document_url or (
        "https://www.gov.br/planejamento/pt-br/assuntos/orcamento/"
        f"orcamentos-anuais/{year}"
    )


STRUCTURED_BREAKS = {
    "educacao_basica": 2024,
}

STRUCTURED_LIMITATIONS = {
    "educacao": [
        "A pergunta foi interpretada como o total do órgão 26000 — Ministério da Educação.",
        "Esse total não equivale necessariamente à função orçamentária Educação.",
        "A composição administrativa do Ministério da Educação pode mudar entre exercícios.",
        "Os valores são autorizações da LOA, não despesas efetivamente pagas.",
    ],
    "fnde": [
        "A cobertura validada inclui os exercícios de 2019 a 2026.",
        "A série representa o total da unidade orçamentária 26298 — FNDE.",
        "Os valores são autorizações da LOA, não despesas efetivamente pagas.",
    ],
    "inss": [
        "A cobertura validada inclui os exercícios de 2019 a 2026.",
        "Em 2022, o total foi reconciliado com o quadro-síntese da unidade 40201, identificado pelo sumário oficial do volume.",
        "A série acompanha as mudanças de código e vinculação institucional do INSS.",
        "Os valores são autorizações da LOA, não despesas efetivamente pagas.",
    ],
    "ministerio_educacao": [
        "A série representa o total do órgão 26000 — Ministério da Educação — e não apenas universidades, FNDE ou institutos federais.",
        "A composição administrativa do Ministério da Educação pode mudar entre exercícios.",
        "Os valores são autorizações da LOA, não despesas efetivamente pagas.",
    ],
    "bolsa_familia": [
        "A série acompanha as mudanças de código e nomenclatura do programa entre os exercícios.",
        "Os valores são autorizações da LOA, não despesas efetivamente pagas.",
    ],
    "cultura": [
        "A série acompanha a mudança do programa Cultura para Direito à Cultura em 2024.",
        "Os valores são autorizações da LOA, não despesas efetivamente pagas.",
    ],
    "defesa": [
        "A comparação considera o programa Defesa Nacional nos Orçamentos Fiscal e da Seguridade Social.",
        "O orçamento de investimento das empresas estatais foi excluído para evitar categorias incompatíveis.",
    ],
    "educacao_superior": [
        "A série começa em 2020 porque a Educação Superior não aparece como programa separado e equivalente em 2019.",
        "O total do programa não deve ser interpretado como orçamento exclusivo das universidades federais.",
        "Os valores são autorizações da LOA, não despesas efetivamente pagas.",
    ],
    "educacao_profissional": [
        "A série começa em 2020 porque a categoria não aparece como programa separado e equivalente em 2019.",
        "O total do programa é mais amplo que o orçamento exclusivo dos Institutos Federais.",
        "A série acompanha a mudança de código e nome do programa em 2024.",
        "Os valores são autorizações da LOA, não despesas efetivamente pagas.",
    ],
    "educacao_basica": [
        "A série começa em 2020 porque a categoria não aparece como programa separado e equivalente em 2019.",
        "Houve mudança relevante de código e escopo em 2024; valores anteriores e posteriores não devem ser comparados diretamente.",
        "Os valores são autorizações da LOA, não despesas efetivamente pagas.",
    ],
}


def _query_years(query: str, selected: list[int]) -> list[int]:
    if selected:
        return sorted(set(selected))
    return sorted({int(year) for year in re.findall(r"\b20(?:19|2[0-6])\b", query)})


def _program_code_response(
    db: Session,
    request: SearchRequest,
    interpretation: QueryInterpretation,
    warnings: list[str],
) -> SearchResponse | None:
    normalized_query = normalize(request.query)
    code_match = re.search(
        r"\bprograma(?:\s+(?:de\s+)?codigo)?\s*[:#-]?\s*(\d{4})\b",
        normalized_query,
    )
    if not code_match:
        return None
    program_code = code_match.group(1)
    query_without_code = (
        normalized_query[: code_match.start()] + normalized_query[code_match.end() :]
    )
    years = _query_years(query_without_code, request.years)
    if len(years) != 1:
        return None
    year = years[0]
    rows = db.execute(
        select(BudgetRecord, Page, DocumentVersion, Document)
        .join(Page, BudgetRecord.page_id == Page.id)
        .join(DocumentVersion, BudgetRecord.document_version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
        .where(
            BudgetRecord.program_code == program_code,
            BudgetRecord.year == year,
        )
        .order_by(DocumentVersion.filename, Page.pdf_page_number)
    ).all()
    distinct_values = {row[0].numeric_value for row in rows}
    if len(rows) != 1 or len(distinct_values) != 1:
        return None

    record, page, version, document = rows[0]
    evidence = Evidence(
        document=document.title,
        year=year,
        pdf_page=page.pdf_page_number,
        printed_page=page.printed_page_label,
        original_text=record.source_text,
        filename=version.filename,
        page_url=f"/documents/{version.id}/pages/{page.pdf_page_number}",
    )
    source = SourceReference(
        id=1,
        document=document.title,
        year=year,
        pdf_page=page.pdf_page_number,
        printed_page=page.printed_page_label,
        excerpt=record.source_text,
        filename=version.filename,
        pdf_url=f"/documents/{version.id}/pdf#page={page.pdf_page_number}",
        official_url=_official_budget_url(document.year, document.official_url),
    )
    name_match = re.search(
        rf"Programa:\s*{re.escape(program_code)}\s+(.*?)\s+Valor do Programa",
        record.source_text,
        re.IGNORECASE,
    )
    program_name = name_match.group(1).strip() if name_match else f"programa {program_code}"
    return SearchResponse(
        query=request.query,
        summary=(
            f"Na LOA de {year}, o valor autorizado para o programa {program_code} "
            f"- {program_name} - foi de R$ {record.original_value} [1]."
        ),
        insufficient_evidence=False,
        evidence=[evidence],
        sources=[source],
        warnings=warnings,
        limitations=[
            "O número após a palavra “programa” foi interpretado como código orçamentário, não como exercício.",
            "O valor é uma autorização da LOA, não uma despesa efetivamente paga.",
        ],
        interpretation=interpretation,
    )


INSTITUTION_CODE_ALIASES = {
    "26000": {"mec"},
    "26104": {"ines"},
    "26105": {"ibc"},
    "26201": {"cpii", "colegio pedro ii"},
    "26256": {"cefet-rj", "cefet rj"},
    "26257": {"cefet-mg", "cefet mg"},
    "26290": {"inep"},
    "26291": {"capes"},
    "26292": {"fundaj"},
    "26294": {"hcpa"},
    "26230": {"univasf"},
    "26231": {"ufal"},
    "26232": {"ufba"},
    "26233": {"ufc"},
    "26234": {"ufes"},
    "26235": {"ufg"},
    "26236": {"uff"},
    "26237": {"ufjf"},
    "26238": {"ufmg"},
    "26239": {"ufpa"},
    "26240": {"ufpb"},
    "26241": {"ufpr"},
    "26242": {"ufpe"},
    "26243": {"ufrn"},
    "26244": {"ufrgs"},
    "26245": {"ufrj"},
    "26246": {"ufsc"},
    "26247": {"ufsm"},
    "26248": {"ufrpe"},
    "26249": {"ufrrj"},
    "26250": {"ufrr"},
    "26251": {"uft"},
    "26252": {"ufcg"},
    "26253": {"ufra"},
    "26254": {"uftm"},
    "26255": {"ufvjm"},
    "26258": {"utfpr"},
    "26260": {"unifal", "unifal-mg"},
    "26261": {"unifei"},
    "26262": {"unifesp"},
    "26263": {"ufla"},
    "26264": {"ufersa"},
    "26266": {"unipampa"},
    "26267": {"unila"},
    "26268": {"unir"},
    "26269": {"unirio"},
    "26270": {"ufam"},
    "26271": {"unb"},
    "26272": {"ufma"},
    "26273": {"furg"},
    "26274": {"ufu"},
    "26275": {"ufac"},
    "26276": {"ufmt"},
    "26277": {"ufop"},
    "26278": {"ufpel"},
    "26279": {"ufpi"},
    "26280": {"ufscar"},
    "26281": {"ufs"},
    "26282": {"ufv"},
    "26283": {"ufms"},
    "26284": {"ufcspa"},
    "26285": {"ufsj"},
    "26286": {"unifap"},
    "26298": {"fnde"},
    "26350": {"ufgd"},
    "26351": {"ufrb"},
    "26352": {"ufabc"},
    "26440": {"uffs"},
    "26441": {"ufopa"},
    "26442": {"unilab"},
    "26443": {"ebserh"},
    "26408": {"ifma"},
    "26414": {"ifmt"},
    "26417": {"ifpb"},
    "26426": {"ifap"},
    "26433": {"ifrj"},
    "26439": {"ifsp"},
    "26447": {"ufob"},
    "26448": {"unifesspa"},
    "26449": {"ufca"},
    "26450": {"ufsb"},
    "26452": {"ufcat"},
    "26453": {"ufj"},
    "26454": {"ufr"},
    "26455": {"ufdpar"},
    "26456": {"ufape"},
    "26457": {"ufnt"},
    "36201": {"fiocruz"},
    "36210": {
        "ghc",
        "grupo hospitalar conceicao",
        "hospital conceicao",
        "hospital nossa senhora da conceicao",
    },
    "36211": {"funasa"},
    "36212": {"anvisa"},
    "36213": {"ans"},
}


EDUCATION_PILOT_ENTITIES = {
    "educacao",
    "ministerio_educacao",
    "universidades_federais",
    "institutos_federais",
    "educacao_superior",
    "educacao_profissional",
    "educacao_basica",
    "fnde",
}


def education_pilot_query_allowed(db: Session, query: str) -> bool:
    """Return True only when the query belongs to the Education pilot scope."""
    parsed = interpret_query(query)
    if parsed["entity"] in EDUCATION_PILOT_ENTITIES:
        return True

    normalized_query = normalize(query)
    education_codes = db.scalars(
        select(BudgetRecord.organization_code)
        .where(
            BudgetRecord.parent_organization_code == "26000",
            BudgetRecord.organization_code.is_not(None),
        )
        .distinct()
    ).all()
    for code in education_codes:
        if not code:
            continue
        if re.search(rf"\b{re.escape(code)}\b", normalized_query):
            return True
        if any(
            re.search(rf"\b{re.escape(normalize(alias))}\b", normalized_query)
            for alias in INSTITUTION_CODE_ALIASES.get(code, set())
        ):
            return True

    education_names = db.scalars(
        select(BudgetRecord.organization_name)
        .where(
            BudgetRecord.parent_organization_code == "26000",
            BudgetRecord.organization_name.is_not(None),
        )
        .distinct()
    ).all()
    return any(
        len(normalize(name)) >= 4 and normalize(name) in normalized_query
        for name in education_names
        if name
    )


def education_pilot_out_of_scope(request: SearchRequest) -> SearchResponse:
    parsed = interpret_query(request.query)
    interpretation = QueryInterpretation(
        **{
            key: value
            for key, value in parsed.items()
            if key
            not in {"search_terms", "available_in_corpus", "requires_structured_values"}
        },
        confirmed=True,
    )
    return SearchResponse(
        query=request.query,
        summary=(
            "Esta versão-piloto responde somente sobre Educação no orçamento federal. "
        ),
        insufficient_evidence=True,
        evidence=[],
        sources=[],
        warnings=["Consulta fora da cobertura do piloto de Educação."],
        limitations=[
            "Saúde, Seguridade Social, Defesa e as demais áreas não estão disponíveis neste piloto.",
            "A ausência de resposta não significa ausência do tema nos documentos originais.",
        ],
        interpretation=interpretation,
    )


def _institution_name(record: BudgetRecord) -> str | None:
    if record.organization_name:
        return record.organization_name
    patterns = (
        r"Unidade universitária federal:\s*\d{5}\s+(?:\d{5}\s*-\s*)?(.*?)\s+Total autorizado",
        r"Órgão:\s*\d{5}\s+(.*?)\s+Total autorizado",
    )
    for pattern in patterns:
        match = re.search(pattern, record.source_text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _institution_aliases(name: str, code: str) -> set[str]:
    normalized_name = normalize(name)
    aliases = {normalized_name, *INSTITUTION_CODE_ALIASES.get(code, set())}
    return {alias for alias in aliases if len(alias) >= 2}


def _multiple_institutions_response(
    request: SearchRequest,
    interpretation: QueryInterpretation,
    warnings: list[str],
    years: list[int],
    candidates: dict[str, tuple[str, list]],
    unresolved_acronyms: list[str],
) -> SearchResponse:
    evidence = []
    sources = []
    institution_series = []
    limitations = [
        "Cada instituição foi vinculada ao respectivo código de unidade orçamentária.",
        "Os valores são autorizações da LOA, não despesas efetivamente pagas.",
    ]
    all_complete = not unresolved_acronyms
    all_selected_rows = []
    for code, (name, rows) in candidates.items():
        rows_by_year: dict[int, list] = {}
        for row in rows:
            rows_by_year.setdefault(row[0].year, []).append(row)
        selected_rows = []
        conflicting_years = []
        for year in years:
            year_rows = rows_by_year.get(year, [])
            distinct_values = {row[0].numeric_value for row in year_rows}
            if len(distinct_values) > 1:
                conflicting_years.append(year)
            elif year_rows:
                selected_rows.append(year_rows[0])
        missing_years = sorted(set(years) - {row[0].year for row in selected_rows})
        if missing_years or conflicting_years:
            all_complete = False
        values = []
        for record, page, version, document in selected_rows:
            source_id = len(sources) + 1
            evidence.append(
                Evidence(
                    document=document.title,
                    year=record.year,
                    pdf_page=page.pdf_page_number,
                    printed_page=page.printed_page_label,
                    original_text=record.source_text,
                    filename=version.filename,
                    page_url=f"/documents/{version.id}/pages/{page.pdf_page_number}",
                )
            )
            sources.append(
                SourceReference(
                    id=source_id,
                    document=document.title,
                    year=record.year,
                    pdf_page=page.pdf_page_number,
                    printed_page=page.printed_page_label,
                    excerpt=record.source_text,
                    filename=version.filename,
                    pdf_url=f"/documents/{version.id}/pdf#page={page.pdf_page_number}",
                    official_url=_official_budget_url(
                        document.year, document.official_url
                    ),
                )
            )
            values.append(
                f"{record.year}: R$ {record.original_value} [{source_id}]"
            )
            all_selected_rows.append((code, name, record, source_id))
        description = (
            f"{name} (código {code}): " + "; ".join(values)
            if values
            else f"{name} (código {code}): nenhum total validado"
        )
        if missing_years:
            description += (
                f"; sem total validado em {', '.join(map(str, missing_years))}"
            )
            limitations.append(
                f"{name}: exercícios sem total validado: "
                f"{', '.join(map(str, missing_years))}."
            )
        if conflicting_years:
            description += (
                f"; totais conflitantes em {', '.join(map(str, conflicting_years))}"
            )
            limitations.append(
                f"{name}: exercícios com totais conflitantes: "
                f"{', '.join(map(str, conflicting_years))}."
            )
        institution_series.append(description + ".")

    summary = "Séries institucionais: " + " ".join(institution_series)
    if interpretation.intent == "compare_maximum" and all_complete:
        maximum = max(all_selected_rows, key=lambda item: item[2].numeric_value)
        summary = (
            f"O maior valor entre as instituições e exercícios selecionados foi o de "
            f"{maximum[1]}, em {maximum[2].year}: "
            f"R$ {maximum[2].original_value} [{maximum[3]}]. "
            + summary
        )
    elif interpretation.intent == "compare_change" and all_complete:
        changes = []
        for code, (name, _) in candidates.items():
            institution_rows = [
                item for item in all_selected_rows if item[0] == code
            ]
            if len(institution_rows) < 2:
                continue
            first, last = institution_rows[0][2], institution_rows[-1][2]
            difference = last.numeric_value - first.numeric_value
            direction = "aumento" if difference >= 0 else "redução"
            formatted = f"{abs(difference):,.0f}".replace(",", ".")
            changes.append(
                f"{name}: {direction} nominal de R$ {formatted} "
                f"entre {first.year} e {last.year}"
            )
        if changes:
            summary += " Variações: " + "; ".join(changes) + "."
    if unresolved_acronyms:
        missing = ", ".join(acronym.upper() for acronym in unresolved_acronyms)
        summary += (
            f" Não encontrei {missing} entre as instituições estruturadas; "
            "a comparação foi limitada às instituições com fontes disponíveis."
        )
        limitations.append(
            f"Instituições não encontradas no acervo consultado: {missing}."
        )
    return SearchResponse(
        query=request.query,
        summary=summary,
        insufficient_evidence=not bool(sources),
        evidence=evidence,
        sources=sources,
        warnings=warnings,
        limitations=limitations,
        interpretation=interpretation,
    )


def _institution_response(
    db: Session,
    request: SearchRequest,
    interpretation: QueryInterpretation,
    warnings: list[str],
) -> SearchResponse | None:
    # Sem filtro ou ano escrito na pergunta, a resposta institucional cobre
    # automaticamente todo o período documental desta versão da aplicação.
    years = _query_years(request.query, request.years) or list(range(2019, 2027))
    rows = db.execute(
        select(BudgetRecord, Page, DocumentVersion, Document)
        .join(Page, BudgetRecord.page_id == Page.id)
        .join(DocumentVersion, BudgetRecord.document_version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
        .where(
            BudgetRecord.year.in_(years),
            BudgetRecord.organization_code.is_not(None),
        )
        .order_by(BudgetRecord.organization_code, BudgetRecord.year)
    ).all()
    normalized_query = normalize(request.query)
    candidates: dict[str, tuple[str, list]] = {}
    recognized_aliases = set()
    for row in rows:
        record = row[0]
        name = _institution_name(record)
        if not name:
            continue
        aliases = _institution_aliases(name, record.organization_code)
        explicit_code = bool(
            re.search(
                rf"\b(?:orgao|unidade|instituicao)(?:\s+de\s+codigo)?\s*"
                rf"[:#-]?\s*{re.escape(record.organization_code)}\b",
                normalized_query,
            )
        )
        matching_aliases = [
            alias
            for alias in aliases
            if (
                alias in normalized_query
                if " " in alias
                else re.search(rf"\b{re.escape(alias)}\b", normalized_query)
            )
        ]
        if not explicit_code and not matching_aliases:
            continue
        recognized_aliases.update(matching_aliases)
        code = record.organization_code
        if code not in candidates:
            candidates[code] = (name, [])
        candidates[code][1].append(row)
    mentioned_acronyms = {
        normalize(acronym)
        for acronym in re.findall(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,12}\b", request.query)
    } - {"loa", "ploa", "ldo", "pldo", "sus"}
    unresolved_acronyms = sorted(
        acronym
        for acronym in mentioned_acronyms
        if acronym not in recognized_aliases
    )
    institution_words = {
        "agencia",
        "autarquia",
        "conselho",
        "fundacao",
        "fundo",
        "instituto",
        "ministerio",
        "tribunal",
        "universidade",
    }
    mentions_institution_name = bool(
        institution_words.intersection(normalized_query.split())
    )
    if not candidates and (unresolved_acronyms or mentions_institution_name):
        missing = (
            ", ".join(acronym.upper() for acronym in unresolved_acronyms)
            if unresolved_acronyms
            else "a instituição mencionada"
        )
        return SearchResponse(
            query=request.query,
            summary=(
                f"Não encontrei {missing} entre as instituições com valores "
                f"estruturados nos exercícios selecionados ({', '.join(map(str, years))}). "
                "Não é seguro apresentar "
                "um orçamento numérico sem uma fonte documental correspondente."
            ),
            insufficient_evidence=True,
            evidence=[],
            sources=[],
            warnings=warnings,
            limitations=[
                "O acervo atual contém somente os PDFs federais definidos para esta versão."
            ],
            interpretation=interpretation,
        )
    if len(candidates) >= 2:
        return _multiple_institutions_response(
            request,
            interpretation,
            warnings,
            years,
            candidates,
            unresolved_acronyms,
        )
    if len(candidates) != 1:
        return None

    code, (name, matched_rows) = next(iter(candidates.items()))
    rows_by_year: dict[int, list] = {}
    for row in matched_rows:
        rows_by_year.setdefault(row[0].year, []).append(row)
    selected_rows = []
    conflicting_years = []
    for year in years:
        year_rows = rows_by_year.get(year, [])
        distinct_values = {row[0].numeric_value for row in year_rows}
        if len(distinct_values) > 1:
            conflicting_years.append(year)
        elif year_rows:
            selected_rows.append(year_rows[0])
    if conflicting_years:
        return SearchResponse(
            query=request.query,
            summary=(
                f"Encontrei totais conflitantes para {name} nos exercícios "
                f"{', '.join(map(str, conflicting_years))}. A comparação foi recusada "
                "até que esses registros sejam revisados."
            ),
            insufficient_evidence=True,
            evidence=[],
            sources=[],
            warnings=warnings,
            limitations=["Há mais de um total documental para o mesmo código e exercício."],
            interpretation=interpretation,
        )
    missing_years = sorted(set(years) - {row[0].year for row in selected_rows})
    if not selected_rows:
        return None

    evidence = []
    sources = []
    values = []
    for source_id, (record, page, version, document) in enumerate(
        selected_rows, start=1
    ):
        evidence.append(
            Evidence(
                document=document.title,
                year=record.year,
                pdf_page=page.pdf_page_number,
                printed_page=page.printed_page_label,
                original_text=record.source_text,
                filename=version.filename,
                page_url=f"/documents/{version.id}/pages/{page.pdf_page_number}",
            )
        )
        sources.append(
            SourceReference(
                id=source_id,
                document=document.title,
                year=record.year,
                pdf_page=page.pdf_page_number,
                printed_page=page.printed_page_label,
                excerpt=record.source_text,
                filename=version.filename,
                pdf_url=f"/documents/{version.id}/pdf#page={page.pdf_page_number}",
                official_url=_official_budget_url(
                    document.year, document.official_url
                ),
            )
        )
        values.append(
            f"{record.year}: R$ {record.original_value} [{source_id}]"
        )

    complete_comparison = not missing_years and not unresolved_acronyms
    if (
        interpretation.intent == "compare_maximum"
        and len(selected_rows) >= 2
        and complete_comparison
    ):
        maximum = max(selected_rows, key=lambda row: row[0].numeric_value)
        source_id = next(
            index
            for index, row in enumerate(selected_rows, start=1)
            if row[0].id == maximum[0].id
        )
        summary = (
            f"Entre {min(years)} e {max(years)}, o maior total autorizado para "
            f"{name} (código {code}) foi o de {maximum[0].year}: "
            f"R$ {maximum[0].original_value} [{source_id}]. "
            "Valores considerados: " + "; ".join(values) + "."
        )
    elif (
        interpretation.intent == "compare_change"
        and len(selected_rows) >= 2
        and complete_comparison
    ):
        first, last = selected_rows[0][0], selected_rows[-1][0]
        difference = last.numeric_value - first.numeric_value
        direction = "um aumento" if difference >= 0 else "uma redução"
        formatted_difference = f"{abs(difference):,.0f}".replace(",", ".")
        summary = (
            f"O total autorizado para {name} (código {code}) passou de "
            f"R$ {first.original_value} em {first.year} [1] para "
            f"R$ {last.original_value} em {last.year} [{len(selected_rows)}], "
            f"{direction} nominal de R$ {formatted_difference}."
        )
    elif len(selected_rows) == 1:
        record = selected_rows[0][0]
        summary = (
            f"Na LOA de {record.year}, o total autorizado para {name} "
            f"(código {code}) foi de R$ {record.original_value} [1]."
        )
    else:
        summary = (
            f"Os totais autorizados para {name} (código {code}) são: "
            + "; ".join(values)
            + "."
        )
    limitations = [
        "A instituição foi identificada pelo nome, sigla ou código vinculado à unidade orçamentária.",
        "O valor é uma autorização da LOA, não uma despesa efetivamente paga.",
    ]
    if missing_years:
        missing_years_text = ", ".join(map(str, missing_years))
        summary += (
            f" Não encontrei um total validado para os exercícios "
            f"{missing_years_text}; por isso, a comparação completa não foi realizada."
        )
        limitations.append(
            f"Exercícios sem total validado para a instituição: {missing_years_text}."
        )
    if unresolved_acronyms:
        missing = ", ".join(acronym.upper() for acronym in unresolved_acronyms)
        summary += (
            f" Não encontrei {missing} entre as instituições estruturadas no acervo; "
            "por isso, a comparação solicitada não foi realizada."
        )
        limitations.append(
            f"Instituição não encontrada no acervo consultado: {missing}."
        )
    return SearchResponse(
        query=request.query,
        summary=summary,
        insufficient_evidence=False,
        evidence=evidence,
        sources=sources,
        warnings=warnings,
        limitations=limitations,
        interpretation=interpretation,
    )


def _universities_response(
    db: Session,
    request: SearchRequest,
    parsed: dict,
    interpretation: QueryInterpretation,
    warnings: list[str],
) -> SearchResponse | None:
    if (
        parsed["entity"] != "universidades_federais"
        or not parsed["requires_structured_values"]
    ):
        return None
    rows = db.execute(
        select(BudgetRecord, Page, DocumentVersion, Document)
        .join(Page, BudgetRecord.page_id == Page.id)
        .join(DocumentVersion, BudgetRecord.document_version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
        .where(BudgetRecord.source_text.startswith("Unidade universitária federal:"))
        .order_by(BudgetRecord.year, Page.pdf_page_number, BudgetRecord.organization_code)
    ).all()
    requested_years = _query_years(request.query, request.years)
    if requested_years:
        rows = [row for row in rows if row[0].year in requested_years]
    by_year: dict[int, list] = {}
    for row in rows:
        by_year.setdefault(row[0].year, []).append(row)
    expected_years = set(requested_years or range(2019, 2027))
    if set(by_year) != expected_years:
        return None

    asks_which_university = bool(
        re.search(
            r"\bqual(?:\s+foi)?\s+(?:a\s+)?universidade(?:\s+federal)?\b",
            normalize(request.query),
        )
    )
    if parsed["intent"] == "compare_maximum" and asks_which_university:
        evidence = []
        sources = []
        annual_leaders = []
        names_by_code: dict[str, list[str]] = {}
        for year_rows in by_year.values():
            for candidate_record, _, _, _ in year_rows:
                candidate_name = _institution_name(candidate_record)
                if candidate_name:
                    names_by_code.setdefault(
                        candidate_record.organization_code, []
                    ).append(candidate_name)
        for source_id, year in enumerate(sorted(by_year), start=1):
            record, page, version, document = max(
                by_year[year], key=lambda row: row[0].numeric_value
            )
            candidate_names = names_by_code.get(record.organization_code, [])
            name = (
                max(set(candidate_names), key=candidate_names.count)
                if candidate_names
                else "Universidade federal"
            )
            annual_leaders.append(
                f"{year}: {name} (código {record.organization_code}), "
                f"R$ {record.original_value} [{source_id}]"
            )
            evidence.append(
                Evidence(
                    document=document.title,
                    year=year,
                    pdf_page=page.pdf_page_number,
                    printed_page=page.printed_page_label,
                    original_text=record.source_text,
                    filename=version.filename,
                    page_url=f"/documents/{version.id}/pages/{page.pdf_page_number}",
                )
            )
            sources.append(
                SourceReference(
                    id=source_id,
                    document=document.title,
                    year=year,
                    pdf_page=page.pdf_page_number,
                    printed_page=page.printed_page_label,
                    excerpt=record.source_text,
                    filename=version.filename,
                    pdf_url=f"/documents/{version.id}/pdf#page={page.pdf_page_number}",
                    official_url=_official_budget_url(
                        document.year, document.official_url
                    ),
                )
            )
        return SearchResponse(
            query=request.query,
            summary=(
                f"As universidades federais com o maior total autorizado em cada "
                f"exercício de {min(expected_years)} a {max(expected_years)} foram: "
                + "; ".join(annual_leaders)
                + "."
            ),
            insufficient_evidence=False,
            evidence=evidence,
            sources=sources,
            warnings=warnings,
            limitations=[
                "A comparação é feita separadamente em cada exercício; valores nominais de anos diferentes não são somados.",
                "Hospitais universitários, EBSERH, FNDE, institutos federais e demais unidades do MEC foram excluídos.",
                "Os valores são autorizações da LOA, não despesas efetivamente pagas.",
            ],
            interpretation=interpretation,
        )

    evidence = []
    sources = []
    totals = {}
    for source_id, year in enumerate(sorted(by_year), start=1):
        components = by_year[year]
        total = sum(record.numeric_value for record, _, _, _ in components)
        totals[year] = total
        first_record, first_page, version, document = components[0]
        pages = sorted({page.pdf_page_number for _, page, _, _ in components})
        page_description = (
            str(pages[0]) if len(pages) == 1 else f"{pages[0]}–{pages[-1]}"
        )
        excerpt = (
            f"Soma de {len(components)} unidades universitárias federais explicitamente "
            f"listadas no Quadro 5. Páginas PDF {page_description}. "
            f"Total calculado: R$ {total:,.0f}".replace(",", ".")
        )
        evidence.append(
            Evidence(
                document=document.title,
                year=year,
                pdf_page=first_page.pdf_page_number,
                printed_page=first_page.printed_page_label,
                original_text=excerpt,
                filename=version.filename,
                page_url=f"/documents/{version.id}/pages/{first_page.pdf_page_number}",
            )
        )
        sources.append(
            SourceReference(
                id=source_id,
                document=document.title,
                year=year,
                pdf_page=first_page.pdf_page_number,
                printed_page=first_page.printed_page_label,
                excerpt=excerpt,
                filename=version.filename,
                pdf_url=f"/documents/{version.id}/pdf#page={first_page.pdf_page_number}",
                official_url=_official_budget_url(document.year, document.official_url),
            )
        )

    values = [
        f"{year}: R$ {totals[year]:,.0f} [{index}]".replace(",", ".")
        for index, year in enumerate(sorted(totals), start=1)
    ]
    if parsed["intent"] == "compare_maximum":
        maximum_year = max(totals, key=totals.get)
        source_id = sorted(totals).index(maximum_year) + 1
        summary = (
            f"Entre {min(totals)} e {max(totals)}, o maior total autorizado para as "
            f"universidades federais foi o de {maximum_year}: "
            f"R$ {totals[maximum_year]:,.0f} [{source_id}]. ".replace(",", ".")
            + "Valores considerados: "
            + "; ".join(values)
            + "."
        )
    elif parsed["intent"] == "compare_change" and len(totals) >= 2:
        first_year, last_year = min(totals), max(totals)
        difference = totals[last_year] - totals[first_year]
        direction = "aumento" if difference >= 0 else "redução"
        summary = (
            f"O total autorizado para as universidades federais passou de "
            f"R$ {totals[first_year]:,.0f} em {first_year} [1] para "
            f"R$ {totals[last_year]:,.0f} em {last_year} [{len(totals)}], "
            f"uma {direction} nominal de R$ {abs(difference):,.0f}. "
        ).replace(",", ".")
    else:
        summary = (
            "Os totais autorizados na LOA para as universidades federais são: "
            + "; ".join(values)
            + "."
        )
    return SearchResponse(
        query=request.query,
        summary=summary,
        insufficient_evidence=False,
        evidence=evidence,
        sources=sources,
        warnings=warnings,
        limitations=[
            "Os totais foram calculados pela soma das unidades orçamentárias identificadas como universidades federais no Quadro 5 de cada LOA.",
            "Hospitais universitários, EBSERH, FNDE, institutos federais e demais unidades do MEC foram excluídos.",
            "A composição passou de 68 unidades em 2019 para 69 unidades a partir de 2020; criações e reorganizações institucionais afetam a comparação.",
            "Os valores são autorizações da LOA, não despesas efetivamente pagas.",
        ],
        interpretation=interpretation,
    )


def _education_institution_count_response(
    db: Session,
    request: SearchRequest,
    parsed: dict,
    interpretation: QueryInterpretation,
    warnings: list[str],
) -> SearchResponse | None:
    group = INSTITUTION_GROUPS.get(parsed["entity"])
    if parsed["intent"] != "count_institutions" or group is None:
        return None
    years = _query_years(request.query, request.years) or list(range(2019, 2027))
    conditions = [
        BudgetRecord.year.in_(years),
        BudgetRecord.parent_organization_code == group["parent_organization_code"],
    ]
    if group["institution_category"]:
        conditions.append(
            BudgetRecord.institution_category == group["institution_category"]
        )
    rows = db.execute(
        select(BudgetRecord, Page, DocumentVersion, Document)
        .join(Page, BudgetRecord.page_id == Page.id)
        .join(DocumentVersion, BudgetRecord.document_version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
        .where(*conditions)
        .order_by(BudgetRecord.year, BudgetRecord.organization_code)
    ).all()
    if not rows:
        return None

    by_year: dict[int, list] = {}
    for row in rows:
        by_year.setdefault(row[0].year, []).append(row)
    values = []
    evidence = []
    sources = []
    missing_years = sorted(set(years) - set(by_year))
    category_label = group["label"]
    for source_id, year in enumerate(sorted(by_year), start=1):
        year_rows = by_year[year]
        count = len({row[0].organization_code for row in year_rows})
        values.append(f"{year}: {count} {category_label} [{source_id}]")
        record, page, version, document = year_rows[0]
        excerpt = (
            f"Contagem de {count} códigos distintos de {category_label} "
            f"no Quadro 5 da LOA de {year}."
        )
        evidence.append(
            Evidence(
                document=document.title,
                year=year,
                pdf_page=page.pdf_page_number,
                printed_page=page.printed_page_label,
                original_text=excerpt,
                filename=version.filename,
                page_url=f"/documents/{version.id}/pages/{page.pdf_page_number}",
            )
        )
        sources.append(
            SourceReference(
                id=source_id,
                document=document.title,
                year=year,
                pdf_page=page.pdf_page_number,
                printed_page=page.printed_page_label,
                excerpt=excerpt,
                filename=version.filename,
                pdf_url=f"/documents/{version.id}/pdf#page={page.pdf_page_number}",
                official_url=_official_budget_url(document.year, document.official_url),
            )
        )
    summary = (
        f"A contagem validada de {category_label}, por código de unidade orçamentária, é: "
        + "; ".join(values)
        + "."
    )
    limitations = [
        "A contagem usa códigos distintos de unidades orçamentárias presentes em cada LOA.",
        "Criações, extinções e mudanças de vinculação podem alterar a quantidade entre exercícios.",
    ]
    if missing_years:
        limitations.append(
            "Exercícios sem contagem validada: " + ", ".join(map(str, missing_years)) + "."
        )
    return SearchResponse(
        query=request.query,
        summary=summary,
        insufficient_evidence=False,
        evidence=evidence,
        sources=sources,
        warnings=warnings,
        limitations=limitations,
        interpretation=interpretation,
    )


def _education_institution_list_response(
    db: Session,
    request: SearchRequest,
    parsed: dict,
    interpretation: QueryInterpretation,
    warnings: list[str],
) -> SearchResponse | None:
    group = INSTITUTION_GROUPS.get(parsed["entity"])
    if parsed["intent"] != "list_institutions" or group is None:
        return None

    years = _query_years(request.query, request.years) or list(range(2019, 2027))
    conditions = [
        BudgetRecord.year.in_(years),
        BudgetRecord.parent_organization_code == group["parent_organization_code"],
    ]
    category_label = group["label"]
    if group["institution_category"]:
        conditions.append(
            BudgetRecord.institution_category == group["institution_category"]
        )

    rows = db.execute(
        select(BudgetRecord, Page, DocumentVersion, Document)
        .join(Page, BudgetRecord.page_id == Page.id)
        .join(DocumentVersion, BudgetRecord.document_version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
        .where(*conditions)
        .order_by(
            BudgetRecord.organization_code,
            BudgetRecord.year.desc(),
        )
    ).all()
    if not rows:
        return None

    normalized_query = normalize(request.query)
    lists_budget_values = any(
        term in normalized_query
        for term in ("orcamento", "valor", "dotacao", "quanto")
    )
    if lists_budget_values:
        listed_units = []
        evidence = []
        sources = []
        source_ids: dict[tuple[int, int], int] = {}
        for record, page, version, document in sorted(
            rows, key=lambda row: (row[0].year, row[0].organization_code)
        ):
            source_key = (version.id, page.pdf_page_number)
            source_id = source_ids.get(source_key)
            if source_id is None:
                source_id = len(sources) + 1
                source_ids[source_key] = source_id
                evidence.append(
                    Evidence(
                        document=document.title,
                        year=document.year,
                        pdf_page=page.pdf_page_number,
                        printed_page=page.printed_page_label,
                        original_text=record.source_text,
                        filename=version.filename,
                        page_url=(
                            f"/documents/{version.id}/pages/{page.pdf_page_number}"
                        ),
                    )
                )
                sources.append(
                    SourceReference(
                        id=source_id,
                        document=document.title,
                        year=document.year,
                        pdf_page=page.pdf_page_number,
                        printed_page=page.printed_page_label,
                        excerpt=record.source_text,
                        filename=version.filename,
                        pdf_url=(
                            f"/documents/{version.id}/pdf#page={page.pdf_page_number}"
                        ),
                        official_url=_official_budget_url(
                            document.year, document.official_url
                        ),
                    )
                )
            listed_units.append(
                ListedUnit(
                    name=_institution_name(record)
                    or f"Unidade {record.organization_code}",
                    code=record.organization_code,
                    category=record.institution_category or "não classificada",
                    years=[record.year],
                    year=record.year,
                    original_value=record.original_value,
                    source_id=source_id,
                )
            )

        institution_count = len(
            {item.code for item in listed_units}
        )
        limitations = [
            "Cada linha representa o total autorizado para uma unidade orçamentária em um exercício.",
            "Os valores são autorizações da LOA, não despesas efetivamente pagas.",
        ]
        if parsed["entity"] == "universidades_federais":
            limitations.append(
                "Nesta aplicação, “universidade” sem outro qualificador significa universidade federal presente no acervo das LOAs da União."
            )
        elif parsed["entity"] == "institutos_federais":
            limitations.append(
                "A categoria reúne 38 Institutos Federais e dois Cefets, identificados separadamente."
            )
        return SearchResponse(
            query=request.query,
            summary=(
                f"Localizei os valores autorizados de {institution_count} "
                f"{category_label}, em {len(years)} exercício"
                f"{'s' if len(years) != 1 else ''}. "
                "A tabela apresenta instituição, código, ano, valor e fonte original."
            ),
            insufficient_evidence=False,
            evidence=evidence,
            sources=sources,
            listed_units=listed_units,
            warnings=warnings,
            limitations=limitations,
            interpretation=interpretation,
        )

    by_code: dict[str, list] = {}
    for row in rows:
        member_key = (
            _institution_name(row[0]) or row[0].organization_code
            if group.get("deduplicate_by_name")
            else row[0].organization_code
        )
        by_code.setdefault(member_key, []).append(row)

    listed_units = []
    evidence = []
    sources = []
    for source_id, member_key in enumerate(sorted(by_code), start=1):
        code_rows = by_code[member_key]
        record, page, version, document = code_rows[0]
        code = record.organization_code
        name = _institution_name(record) or f"Unidade {code}"
        available_years = sorted({item[0].year for item in code_rows})
        listed_units.append(
            ListedUnit(
                name=name,
                code=code,
                category=record.institution_category or "não classificada",
                years=available_years,
                source_id=source_id,
            )
        )
        evidence.append(
            Evidence(
                document=document.title,
                year=document.year,
                pdf_page=page.pdf_page_number,
                printed_page=page.printed_page_label,
                original_text=record.source_text,
                filename=version.filename,
                page_url=f"/documents/{version.id}/pages/{page.pdf_page_number}",
            )
        )
        sources.append(
            SourceReference(
                id=source_id,
                document=document.title,
                year=document.year,
                pdf_page=page.pdf_page_number,
                printed_page=page.printed_page_label,
                excerpt=record.source_text,
                filename=version.filename,
                pdf_url=f"/documents/{version.id}/pdf#page={page.pdf_page_number}",
                official_url=_official_budget_url(document.year, document.official_url),
            )
        )

    limitations = [
        (
            "A listagem consolida mudanças de código pelo nome validado da instituição."
            if group.get("deduplicate_by_name")
            else "A listagem usa códigos distintos de unidades orçamentárias presentes nas LOAs selecionadas."
        ),
        "O período exibido informa em quais exercícios cada código aparece no acervo.",
    ]
    if parsed["entity"] == "institutos_federais":
        limitations.append(
            "A classificação de educação profissional contém 38 Institutos Federais e dois Cefets; os Cefets são identificados separadamente na tabela."
        )
    elif parsed["entity"] == "universidades_federais":
        limitations.append(
            "Nesta aplicação, “universidade” sem outro qualificador significa universidade federal presente no acervo das LOAs da União."
        )
    return SearchResponse(
        query=request.query,
        summary=(
            f"Localizei {len(listed_units)} {category_label} no período de "
            f"{min(years)} a {max(years)}. "
            "A relação nominal, os códigos e as fontes estão na tabela abaixo."
        ),
        insufficient_evidence=False,
        evidence=evidence,
        sources=sources,
        listed_units=listed_units,
        warnings=warnings,
        limitations=limitations,
        interpretation=interpretation,
    )


def _education_institution_ranking_response(
    db: Session,
    request: SearchRequest,
    parsed: dict,
    interpretation: QueryInterpretation,
    warnings: list[str],
) -> SearchResponse | None:
    if parsed["intent"] != "compare_maximum" or parsed["entity"] != "educacao":
        return None
    normalized_query = normalize(request.query)
    if any(
        phrase in normalized_query
        for phrase in (
            "ranking",
            "ordene",
            "ordenar",
            "do maior para o menor",
            "da maior para a menor",
        )
    ):
        return None
    if not any(term in normalized_query for term in ("instituicao", "unidade", "orgao")):
        return None
    years = _query_years(request.query, request.years) or list(range(2019, 2027))
    rows = db.execute(
        select(BudgetRecord, Page, DocumentVersion, Document)
        .join(Page, BudgetRecord.page_id == Page.id)
        .join(DocumentVersion, BudgetRecord.document_version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
        .where(
            BudgetRecord.year.in_(years),
            BudgetRecord.parent_organization_code == "26000",
        )
        .order_by(BudgetRecord.year, BudgetRecord.numeric_value.desc())
    ).all()
    if not rows:
        return None

    leaders = {}
    for row in rows:
        leaders.setdefault(row[0].year, row)
    evidence = []
    sources = []
    values = []
    for source_id, year in enumerate(sorted(leaders), start=1):
        record, page, version, document = leaders[year]
        name = _institution_name(record) or f"unidade {record.organization_code}"
        values.append(
            f"{year}: {name} (código {record.organization_code}), "
            f"R$ {record.original_value} [{source_id}]"
        )
        evidence.append(
            Evidence(
                document=document.title,
                year=year,
                pdf_page=page.pdf_page_number,
                printed_page=page.printed_page_label,
                original_text=record.source_text,
                filename=version.filename,
                page_url=f"/documents/{version.id}/pages/{page.pdf_page_number}",
            )
        )
        sources.append(
            SourceReference(
                id=source_id,
                document=document.title,
                year=year,
                pdf_page=page.pdf_page_number,
                printed_page=page.printed_page_label,
                excerpt=record.source_text,
                filename=version.filename,
                pdf_url=f"/documents/{version.id}/pdf#page={page.pdf_page_number}",
                official_url=_official_budget_url(document.year, document.official_url),
            )
        )
    missing_years = sorted(set(years) - set(leaders))
    limitations = [
        "O ranking compara unidades orçamentárias vinculadas ao MEC, sem somar instituições distintas.",
        "Os valores são autorizações da LOA, não despesas efetivamente pagas.",
    ]
    if missing_years:
        limitations.append(
            "Exercícios sem ranking validado: " + ", ".join(map(str, missing_years)) + "."
        )
    return SearchResponse(
        query=request.query,
        summary="As unidades da Educação com maior orçamento autorizado foram: "
        + "; ".join(values)
        + ".",
        insufficient_evidence=bool(missing_years),
        evidence=evidence,
        sources=sources,
        warnings=warnings,
        limitations=limitations,
        interpretation=interpretation,
    )


def _category_member_ranking_response(
    db: Session,
    request: SearchRequest,
    parsed: dict,
    interpretation: QueryInterpretation,
    warnings: list[str],
) -> SearchResponse | None:
    category_config = CATEGORY_MEMBER_RANKINGS.get(parsed["entity"])
    if category_config is None or parsed["intent"] != "compare_maximum":
        return None

    normalized_query = normalize(request.query)
    asks_for_full_ranking = any(
        phrase in normalized_query
        for phrase in (
            "ranking",
            "ordene",
            "ordenar",
            "do maior para o menor",
            "da maior para a menor",
        )
    )
    asks_for_year = any(
        phrase in normalized_query
        for phrase in ("em que ano", "qual ano", "maior total", "total dos")
    )
    member_expression = "|".join(category_config["member_terms"])
    asks_for_member = bool(
        re.search(
            r"\bqual(?:\s+(?:e|foi))?\s+(?:o|a)?\s*"
            rf"(?:{member_expression})\b",
            normalized_query,
        )
        or re.search(
            rf"\b(?:{member_expression})\b.*\bmaior\b",
            normalized_query,
        )
    )
    if not asks_for_year and not asks_for_member and not asks_for_full_ranking:
        return None

    category = category_config["institution_category"]
    category_label = category_config["label"]
    years = _query_years(request.query, request.years) or list(range(2019, 2027))
    conditions = [
        BudgetRecord.year.in_(years),
        BudgetRecord.parent_organization_code
        == category_config["parent_organization_code"],
    ]
    if category:
        conditions.append(BudgetRecord.institution_category == category)
    rows = db.execute(
        select(BudgetRecord, Page, DocumentVersion, Document)
        .join(Page, BudgetRecord.page_id == Page.id)
        .join(DocumentVersion, BudgetRecord.document_version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
        .where(*conditions)
        .order_by(BudgetRecord.year, BudgetRecord.numeric_value.desc())
    ).all()
    if not rows:
        return None

    if asks_for_year:
        totals: dict[int, int] = {}
        evidence = []
        sources = []
        source_ids: dict[tuple[int, int], int] = {}
        year_source_ids: dict[int, list[int]] = {}
        for record, page, version, document in rows:
            totals[record.year] = totals.get(record.year, 0) + int(
                record.numeric_value
            )
            source_key = (version.id, page.pdf_page_number)
            source_id = source_ids.get(source_key)
            if source_id is None:
                source_id = len(sources) + 1
                source_ids[source_key] = source_id
                evidence.append(
                    Evidence(
                        document=document.title,
                        year=record.year,
                        pdf_page=page.pdf_page_number,
                        printed_page=page.printed_page_label,
                        original_text=record.source_text,
                        filename=version.filename,
                        page_url=(
                            f"/documents/{version.id}/pages/{page.pdf_page_number}"
                        ),
                    )
                )
                sources.append(
                    SourceReference(
                        id=source_id,
                        document=document.title,
                        year=record.year,
                        pdf_page=page.pdf_page_number,
                        printed_page=page.printed_page_label,
                        excerpt=record.source_text,
                        filename=version.filename,
                        pdf_url=(
                            f"/documents/{version.id}/pdf#page={page.pdf_page_number}"
                        ),
                        official_url=_official_budget_url(
                            document.year, document.official_url
                        ),
                    )
                )
            if source_id not in year_source_ids.setdefault(record.year, []):
                year_source_ids[record.year].append(source_id)

        values = []
        for year in sorted(totals):
            citations = " ".join(f"[{source_id}]" for source_id in year_source_ids[year])
            formatted_total = f"{totals[year]:,.0f}".replace(",", ".")
            values.append(f"{year}: R$ {formatted_total} {citations}")
        highest_year = max(totals, key=totals.get)
        highest_total = f"{totals[highest_year]:,.0f}".replace(",", ".")
        return SearchResponse(
            query=request.query,
            summary=(
                f"O maior total agregado das {category_label} ocorreu em "
                f"{highest_year}: R$ {highest_total}. Totais anuais: "
                + "; ".join(values)
                + "."
            ),
            insufficient_evidence=False,
            evidence=evidence,
            sources=sources,
            warnings=warnings,
            limitations=[
                f"O total anual soma individualmente as {category_label} validadas em cada exercício.",
                "Mudanças de código da mesma instituição não geram soma duplicada dentro do mesmo exercício.",
                "Os valores são autorizações da LOA, não despesas efetivamente pagas.",
                *category_config["limitations"],
            ],
            interpretation=interpretation,
        )

    if asks_for_full_ranking:
        listed_units = []
        evidence = []
        sources = []
        source_ids: dict[tuple[int, int], int] = {}
        for record, page, version, document in rows:
            source_key = (version.id, page.pdf_page_number)
            source_id = source_ids.get(source_key)
            if source_id is None:
                source_id = len(sources) + 1
                source_ids[source_key] = source_id
                evidence.append(
                    Evidence(
                        document=document.title,
                        year=record.year,
                        pdf_page=page.pdf_page_number,
                        printed_page=page.printed_page_label,
                        original_text=record.source_text,
                        filename=version.filename,
                        page_url=f"/documents/{version.id}/pages/{page.pdf_page_number}",
                    )
                )
                sources.append(
                    SourceReference(
                        id=source_id,
                        document=document.title,
                        year=record.year,
                        pdf_page=page.pdf_page_number,
                        printed_page=page.printed_page_label,
                        excerpt=record.source_text,
                        filename=version.filename,
                        pdf_url=f"/documents/{version.id}/pdf#page={page.pdf_page_number}",
                        official_url=_official_budget_url(
                            document.year, document.official_url
                        ),
                    )
                )
            listed_units.append(
                ListedUnit(
                    name=_institution_name(record)
                    or f"Unidade {record.organization_code}",
                    code=record.organization_code,
                    category=record.institution_category or "não classificada",
                    years=[record.year],
                    year=record.year,
                    original_value=record.original_value,
                    source_id=source_id,
                )
            )

        scope = (
            f"em {years[0]}"
            if len(years) == 1
            else f"em cada exercício de {min(years)} a {max(years)}"
        )
        limitations = [
            f"O ranking ordena individualmente as {category_label}, sem somar instituições distintas.",
            "Dentro de cada exercício, as linhas aparecem do maior para o menor orçamento autorizado.",
            "Os valores são autorizações da LOA, não despesas efetivamente pagas.",
            *category_config["limitations"],
        ]
        return SearchResponse(
            query=request.query,
            summary=(
                f"Ranking de orçamento autorizado das {category_label}, {scope}. "
                "A tabela está ordenada do maior para o menor valor em cada exercício."
            ),
            insufficient_evidence=False,
            evidence=evidence,
            sources=sources,
            listed_units=listed_units,
            warnings=warnings,
            limitations=limitations,
            interpretation=interpretation,
        )

    leaders = {}
    for row in rows:
        leaders.setdefault(row[0].year, row)

    evidence = []
    sources = []
    values = []
    for source_id, year in enumerate(sorted(leaders), start=1):
        record, page, version, document = leaders[year]
        name = _institution_name(record) or f"Unidade {record.organization_code}"
        values.append(
            f"{year}: {name} (código {record.organization_code}), "
            f"R$ {record.original_value} [{source_id}]"
        )
        evidence.append(
            Evidence(
                document=document.title,
                year=year,
                pdf_page=page.pdf_page_number,
                printed_page=page.printed_page_label,
                original_text=record.source_text,
                filename=version.filename,
                page_url=f"/documents/{version.id}/pages/{page.pdf_page_number}",
            )
        )
        sources.append(
            SourceReference(
                id=source_id,
                document=document.title,
                year=year,
                pdf_page=page.pdf_page_number,
                printed_page=page.printed_page_label,
                excerpt=record.source_text,
                filename=version.filename,
                pdf_url=f"/documents/{version.id}/pdf#page={page.pdf_page_number}",
                official_url=_official_budget_url(document.year, document.official_url),
            )
        )

    missing_years = sorted(set(years) - set(leaders))
    limitations = [
        f"O ranking compara individualmente as {category_label}, sem somar instituições distintas.",
        "Os valores são autorizações da LOA, não despesas efetivamente pagas.",
        *category_config["limitations"],
    ]
    if missing_years:
        limitations.append(
            "Exercícios sem ranking validado: " + ", ".join(map(str, missing_years)) + "."
        )
    scope = (
        f"em {years[0]}"
        if len(years) == 1
        else f"em cada exercício de {min(years)} a {max(years)}"
    )
    return SearchResponse(
        query=request.query,
        summary=(
            f"As unidades com maior orçamento autorizado entre as {category_label}, "
            f"{scope}, foram: " + "; ".join(values) + "."
        ),
        insufficient_evidence=bool(missing_years),
        evidence=evidence,
        sources=sources,
        warnings=warnings,
        limitations=limitations,
        interpretation=interpretation,
    )


def _education_category_response(
    db: Session,
    request: SearchRequest,
    parsed: dict,
    interpretation: QueryInterpretation,
    warnings: list[str],
) -> SearchResponse | None:
    categories = {
        "institutos_federais": (
            "educacao_profissional",
            "Institutos Federais",
        ),
    }
    selected = categories.get(parsed["entity"])
    if selected is None or not parsed["requires_structured_values"]:
        return None
    category, label = selected
    years = _query_years(request.query, request.years) or list(range(2019, 2027))
    rows = db.execute(
        select(BudgetRecord, Page, DocumentVersion, Document)
        .join(Page, BudgetRecord.page_id == Page.id)
        .join(DocumentVersion, BudgetRecord.document_version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
        .where(
            BudgetRecord.year.in_(years),
            BudgetRecord.parent_organization_code == "26000",
            BudgetRecord.institution_category == category,
        )
        .order_by(BudgetRecord.year, Page.pdf_page_number, BudgetRecord.organization_code)
    ).all()
    by_year: dict[int, list] = {}
    for row in rows:
        by_year.setdefault(row[0].year, []).append(row)
    if set(by_year) != set(years):
        return None

    totals = {}
    evidence = []
    sources = []
    for source_id, year in enumerate(sorted(by_year), start=1):
        components = by_year[year]
        totals[year] = sum(record.numeric_value for record, _, _, _ in components)
        first_record, first_page, version, document = components[0]
        pages = sorted({page.pdf_page_number for _, page, _, _ in components})
        excerpt = (
            f"Soma de {len(components)} unidades classificadas como {label} no Quadro 5. "
            f"Páginas PDF {pages[0]}–{pages[-1]}. "
            f"Total calculado: R$ {totals[year]:,.0f}"
        ).replace(",", ".")
        evidence.append(
            Evidence(
                document=document.title,
                year=year,
                pdf_page=first_page.pdf_page_number,
                printed_page=first_page.printed_page_label,
                original_text=excerpt,
                filename=version.filename,
                page_url=f"/documents/{version.id}/pages/{first_page.pdf_page_number}",
            )
        )
        sources.append(
            SourceReference(
                id=source_id,
                document=document.title,
                year=year,
                pdf_page=first_page.pdf_page_number,
                printed_page=first_page.printed_page_label,
                excerpt=excerpt,
                filename=version.filename,
                pdf_url=f"/documents/{version.id}/pdf#page={first_page.pdf_page_number}",
                official_url=_official_budget_url(document.year, document.official_url),
            )
        )
    values = [
        f"{year}: R$ {totals[year]:,.0f} [{index}]".replace(",", ".")
        for index, year in enumerate(sorted(totals), start=1)
    ]
    if parsed["intent"] == "compare_maximum":
        maximum_year = max(totals, key=totals.get)
        source_id = sorted(totals).index(maximum_year) + 1
        maximum_value = f"{totals[maximum_year]:,.0f}".replace(",", ".")
        summary = (
            f"Entre {min(totals)} e {max(totals)}, o maior total autorizado para os "
            f"{label} foi o de {maximum_year}: "
            f"R$ {maximum_value} [{source_id}]. Valores considerados: "
        ) + "; ".join(values) + "."
    elif parsed["intent"] == "compare_change" and len(totals) >= 2:
        first_year, last_year = min(totals), max(totals)
        difference = totals[last_year] - totals[first_year]
        direction = "aumento" if difference >= 0 else "redução"
        first_value = f"{totals[first_year]:,.0f}".replace(",", ".")
        last_value = f"{totals[last_year]:,.0f}".replace(",", ".")
        difference_value = f"{abs(difference):,.0f}".replace(",", ".")
        summary = (
            f"O total autorizado para os {label} passou de "
            f"R$ {first_value} em {first_year} [1] para "
            f"R$ {last_value} em {last_year} [{len(totals)}], "
            f"uma {direction} nominal de R$ {difference_value}."
        )
    else:
        summary = f"Os totais autorizados na LOA para os {label} são: " + "; ".join(values) + "."
    return SearchResponse(
        query=request.query,
        summary=summary,
        insufficient_evidence=False,
        evidence=evidence,
        sources=sources,
        warnings=warnings,
        limitations=[
            f"Cada total soma {len(by_year[min(by_year)])} unidades orçamentárias classificadas como {label}.",
            "Os valores são autorizações da LOA, não despesas efetivamente pagas.",
        ],
        interpretation=interpretation,
    )


def _structured_program_response(
    db: Session,
    request: SearchRequest,
    parsed: dict,
    interpretation: QueryInterpretation,
    warnings: list[str],
) -> SearchResponse | None:
    codes_by_year = STRUCTURED_PROGRAM_CODES.get(parsed["entity"])
    if not codes_by_year or not parsed["requires_structured_values"]:
        return None
    entity_field_name = STRUCTURED_ENTITY_FIELDS.get(parsed["entity"], "program_code")
    entity_field = getattr(BudgetRecord, entity_field_name)
    rows = db.execute(
        select(BudgetRecord, Page, DocumentVersion, Document)
        .join(Page, BudgetRecord.page_id == Page.id)
        .join(DocumentVersion, BudgetRecord.document_version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
        .where(entity_field.in_(set(codes_by_year.values())))
        .order_by(BudgetRecord.year)
    ).all()
    preferred_files = STRUCTURED_SOURCE_FILES.get(parsed["entity"], {})
    records = [
        row
        for row in rows
        if codes_by_year.get(row[0].year) == getattr(row[0], entity_field_name)
        and (
            not preferred_files.get(row[0].year)
            or preferred_files[row[0].year] == row[2].filename
        )
    ]
    requested_years = _query_years(request.query, request.years)
    if requested_years:
        records = [row for row in records if row[0].year in requested_years]
    found_years = {row[0].year for row in records}
    expected_years = set(requested_years or codes_by_year)
    if found_years != expected_years:
        return None

    evidence = []
    sources = []
    for index, (record, page, version, document) in enumerate(records, start=1):
        evidence.append(
            Evidence(
                document=document.title,
                year=record.year,
                pdf_page=page.pdf_page_number,
                printed_page=page.printed_page_label,
                original_text=record.source_text,
                filename=version.filename,
                page_url=f"/documents/{version.id}/pages/{page.pdf_page_number}",
            )
        )
        sources.append(
            SourceReference(
                id=index,
                document=document.title,
                year=record.year,
                pdf_page=page.pdf_page_number,
                printed_page=page.printed_page_label,
                excerpt=record.source_text,
                filename=version.filename,
                pdf_url=f"/documents/{version.id}/pdf#page={page.pdf_page_number}",
                official_url=_official_budget_url(document.year, document.official_url),
            )
        )

    label = parsed["entity_label"]
    values = [
        f"{record.year}: R$ {record.original_value} [{index}]"
        for index, (record, _, _, _) in enumerate(records, start=1)
    ]
    break_year = STRUCTURED_BREAKS.get(parsed["entity"])
    spans_break = bool(
        break_year
        and min(expected_years) < break_year <= max(expected_years)
        and parsed["intent"] in {"compare_maximum", "compare_change"}
    )
    if spans_break:
        summary = (
            f"Não é seguro produzir uma comparação única para {label}: houve uma "
            f"mudança relevante de escopo em {break_year}. Os valores documentados "
            "são: " + "; ".join(values) + "."
        )
    elif parsed["intent"] == "compare_maximum":
        maximum = max(records, key=lambda row: row[0].numeric_value)
        source_id = next(
            index
            for index, row in enumerate(records, start=1)
            if row[0].id == maximum[0].id
        )
        summary = (
            f"Entre {min(expected_years)} e {max(expected_years)}, o maior valor "
            f"autorizado na LOA para {label} foi o de {maximum[0].year}: "
            f"R$ {maximum[0].original_value} [{source_id}]. "
            "Valores considerados: " + "; ".join(values) + "."
        )
    elif parsed["intent"] == "compare_change" and len(records) >= 2:
        first, last = records[0][0], records[-1][0]
        direction = "aumento" if last.numeric_value >= first.numeric_value else "redução"
        direction_with_article = (
            "um aumento" if direction == "aumento" else "uma redução"
        )
        difference = abs(last.numeric_value - first.numeric_value)
        formatted_difference = f"{difference:,.0f}".replace(",", ".")
        summary = (
            f"O valor autorizado para {label} passou de R$ {first.original_value} "
            f"em {first.year} [1] para R$ {last.original_value} em {last.year} "
            f"[{len(records)}], {direction_with_article} nominal de R$ {formatted_difference}. "
            "Série consultada: " + "; ".join(values) + "."
        )
    else:
        summary = (
            f"Os valores autorizados na LOA para {label} são: "
            + "; ".join(values)
            + "."
        )
    return SearchResponse(
        query=request.query,
        summary=summary,
        insufficient_evidence=bool(
            STRUCTURED_MISSING_YEARS.get(parsed["entity"], set())
        ),
        evidence=evidence,
        sources=sources,
        warnings=warnings,
        limitations=STRUCTURED_LIMITATIONS.get(parsed["entity"], []),
        interpretation=interpretation,
    )


def search_documents(db: Session, request: SearchRequest) -> SearchResponse:
    parsed = interpret_query(request.query)
    interpretation = QueryInterpretation(
        **{
            key: value
            for key, value in parsed.items()
            if key
            not in {"search_terms", "available_in_corpus", "requires_structured_values"}
        },
        confirmed=request.interpretation_confirmed,
    )
    warnings = ambiguity_warnings(request.query)
    if parsed["requires_confirmation"] and not request.interpretation_confirmed:
        return SearchResponse(
            query=request.query,
            summary=(
                f"Entendi sua pergunta como: {parsed['normalized_query']} "
                "Confirme essa interpretação antes de consultar o acervo."
            ),
            insufficient_evidence=False,
            evidence=[],
            warnings=[parsed["confirmation_reason"]] if parsed["confirmation_reason"] else [],
            interpretation=interpretation,
        )
    if not parsed["available_in_corpus"] or is_execution_query(request.query):
        return SearchResponse(
            query=request.query,
            summary=(
                "Entendi que você deseja consultar execução orçamentária. "
                "O acervo atual contém valores autorizados nas LOAs, mas não comprova "
                "empenhos, liquidações ou pagamentos."
            ),
            insufficient_evidence=True,
            evidence=[],
            warnings=warnings,
            interpretation=interpretation,
        )
    program_code_response = _program_code_response(
        db, request, interpretation, warnings
    )
    if program_code_response is not None:
        return program_code_response
    institution_count_response = _education_institution_count_response(
        db, request, parsed, interpretation, warnings
    )
    if institution_count_response is not None:
        return institution_count_response
    institution_list_response = _education_institution_list_response(
        db, request, parsed, interpretation, warnings
    )
    if institution_list_response is not None:
        return institution_list_response
    education_ranking_response = _education_institution_ranking_response(
        db, request, parsed, interpretation, warnings
    )
    if education_ranking_response is not None:
        return education_ranking_response
    category_member_ranking_response = _category_member_ranking_response(
        db, request, parsed, interpretation, warnings
    )
    if category_member_ranking_response is not None:
        return category_member_ranking_response
    universities_response = _universities_response(
        db, request, parsed, interpretation, warnings
    )
    if universities_response is not None:
        return universities_response
    education_category_response = _education_category_response(
        db, request, parsed, interpretation, warnings
    )
    if education_category_response is not None:
        return education_category_response
    structured_response = _structured_program_response(
        db, request, parsed, interpretation, warnings
    )
    if structured_response is not None:
        return structured_response
    institution_response = _institution_response(
        db, request, interpretation, warnings
    )
    if institution_response is not None:
        return institution_response
    terms = []
    for search_term in parsed["search_terms"]:
        terms.extend(_terms(search_term))
    terms = list(dict.fromkeys(terms))[:12]
    statement: Select = (
        select(Chunk, Page, DocumentVersion, Document)
        .join(Page, Chunk.page_id == Page.id)
        .join(DocumentVersion, Page.version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
    )
    if request.years:
        statement = statement.where(Document.year.in_(request.years))
    if terms:
        statement = statement.where(
            or_(*(Chunk.normalized_text.ilike(f"%{normalize(term)}%") for term in terms))
        )
    rows = db.execute(statement.limit(max(request.limit * 20, 100))).all()
    query_vector = embed(request.query)
    normalized_query = normalize(request.query)
    ranked = []
    for chunk, page, version, document in rows:
        vector = json.loads(chunk.embedding_json) if chunk.embedding_json else []
        semantic = cosine(query_vector, vector) if vector else 0.0
        exact = 1.0 if normalized_query in chunk.normalized_text else 0.0
        coverage = sum(normalize(term) in chunk.normalized_text for term in terms)
        score = exact * 5 + coverage * 1.5 + semantic
        ranked.append((score, chunk, page, version, document))
    ranked.sort(key=lambda row: (-row[0], -row[4].year, row[2].pdf_page_number))
    evidence = [
        Evidence(
            document=document.title,
            year=document.year,
            pdf_page=page.pdf_page_number,
            printed_page=page.printed_page_label,
            original_text=chunk.original_text,
            filename=version.filename,
            page_url=f"/documents/{version.id}/pages/{page.pdf_page_number}",
        )
        for _, chunk, page, version, document in ranked[: request.limit]
    ]
    sources = []
    seen_pages = set()
    for item in evidence:
        page_key = (item.filename, item.pdf_page)
        if page_key in seen_pages:
            continue
        seen_pages.add(page_key)
        version_id = item.page_url.split("/")[2]
        sources.append(
            SourceReference(
                id=len(sources) + 1,
                document=item.document,
                year=item.year,
                pdf_page=item.pdf_page,
                printed_page=item.printed_page,
                excerpt=item.original_text,
                filename=item.filename,
                pdf_url=f"/documents/{version_id}/pdf#page={item.pdf_page}",
                official_url=_official_budget_url(item.year),
            )
        )
        if len(sources) == 5:
            break
    citations = " ".join(f"[{source.id}]" for source in sources)
    if evidence and parsed["requires_structured_values"]:
        summary = (
            f"Entendi sua pergunta como: {parsed['normalized_query']} "
            "Localizei evidências relacionadas, mas os valores anuais ainda não estão "
            "estruturados e validados o suficiente para produzir a comparação. "
            f"Consulte as informações originais nas fontes {citations}."
        )
    elif evidence:
        summary = (
            f"Entendi sua pergunta como: {parsed['normalized_query']} "
            f"As informações originais estão nas fontes {citations}."
        )
    else:
        summary = INSUFFICIENT_EVIDENCE
    return SearchResponse(
        query=request.query,
        summary=summary,
        insufficient_evidence=not evidence,
        evidence=evidence,
        sources=sources,
        warnings=warnings,
        limitations=(
            [
                "Os valores relacionados ainda não estão consolidados em uma série anual comparável."
            ]
            if parsed["requires_structured_values"]
            else []
        ),
        interpretation=interpretation,
    )
