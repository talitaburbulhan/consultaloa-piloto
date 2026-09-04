import re


INSUFFICIENT_EVIDENCE = (
    "Não foram encontradas evidências documentais suficientes para confirmar "
    "esta informação nas Leis Orçamentárias Anuais atualmente indexadas."
)

EXECUTION_PATTERN = re.compile(
    r"\b(empenh|pag[oa]|pagamento|liquida|execuç|restos a pagar)\w*",
    re.I,
)


def has_explicit_year_context(query: str, candidate: str) -> bool:
    patterns = (
        rf"\b(?:em|no ano de|exercício|loa)\s+{re.escape(candidate)}\b",
        rf"\b{re.escape(candidate)}\s+(?:e|x|versus|contra)\s+\d{{4}}\b",
        rf"\b(?:de|entre)\s+{re.escape(candidate)}\s+(?:a|até|e)\s+20\d{{2}}\b",
        rf"\b(?:de|entre)\s+20\d{{2}}\s+(?:a|até|e)\s+{re.escape(candidate)}\b",
        rf"\b{re.escape(candidate)}\s*[–—-]\s*20\d{{2}}\b",
        rf"\b20\d{{2}}\s*[–—-]\s*{re.escape(candidate)}\b",
    )
    return any(re.search(pattern, query, re.IGNORECASE) for pattern in patterns)


def ambiguity_warnings(query: str) -> list[str]:
    warnings: list[str] = []
    for candidate in set(re.findall(r"\b20\d{2}\b", query)):
        if not has_explicit_year_context(query, candidate):
            warnings.append(
                f"“{candidate}” pode representar um exercício ou um código "
                "orçamentário; o contexto foi preservado como ambíguo."
            )
    if is_execution_query(query):
        warnings.append(
            "O acervo contém LOAs, não dados suficientes de execução orçamentária."
        )
    return warnings


def is_execution_query(query: str) -> bool:
    return bool(EXECUTION_PATTERN.search(query))
