from functools import lru_cache
from difflib import SequenceMatcher
from pathlib import Path

import yaml

from .chunking import normalize


IGNORED_QUERY_WORDS = {
    "a",
    "as",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "foi",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "um",
    "uma",
}


def _meaningful_tokens(text: str) -> list[str]:
    return [
        token
        for token in normalize(text).split()
        if token not in IGNORED_QUERY_WORDS
    ]


def _phrase_match_score(phrase: str, text: str) -> float:
    phrase_tokens = _meaningful_tokens(phrase)
    text_tokens = _meaningful_tokens(text)
    if not phrase_tokens or not text_tokens:
        return 0.0
    phrase_text = " ".join(phrase_tokens)
    text_text = " ".join(text_tokens)
    if phrase_text in text_text:
        return 1.0

    size = len(phrase_tokens)
    best = 0.0
    for window_size in {max(1, size - 1), size, size + 1}:
        for start in range(max(0, len(text_tokens) - window_size + 1)):
            candidate = " ".join(text_tokens[start : start + window_size])
            best = max(best, SequenceMatcher(None, phrase_text, candidate).ratio())
    return best


@lru_cache
def load_vocabulary() -> dict:
    root = Path(__file__).resolve().parents[3]
    path = root / "config" / "vocabulario_editorial.yml"
    with path.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def interpret_query(query: str) -> dict:
    vocabulary = load_vocabulary()
    normalized = normalize(query)
    entity_key = None
    entity_data = None
    best_alias_length = -1
    best_alias_score = 0.0
    for key, candidate in vocabulary["entities"].items():
        for alias in candidate["aliases"]:
            normalized_alias = normalize(alias)
            score = _phrase_match_score(alias, query)
            if score >= 0.86 and (
                score > best_alias_score
                or (score == best_alias_score and len(normalized_alias) > best_alias_length)
            ):
                entity_key = key
                entity_data = candidate
                best_alias_length = len(normalized_alias)
                best_alias_score = score

    intent_key = "generic_search"
    intent_data = vocabulary["intents"]["generic_search"]
    best_expression_length = -1
    best_expression_score = 0.0
    for key, candidate in vocabulary["intents"].items():
        for expression in candidate.get("expressions", []):
            normalized_expression = normalize(expression)
            score = _phrase_match_score(expression, query)
            if score >= 0.86 and (
                score > best_expression_score
                or (
                    score == best_expression_score
                    and len(normalized_expression) > best_expression_length
                )
            ):
                intent_key = key
                intent_data = candidate
                best_expression_length = len(normalized_expression)
                best_expression_score = score

    entity_label = entity_data["label"] if entity_data else "o tema consultado"
    normalized_query = intent_data["normalized_template"].format(entity=entity_label)
    requires_confirmation = bool(entity_data and entity_data.get("ambiguous_scope"))
    reason = None
    if "receita" in normalized and intent_key in {
        "compare_maximum",
        "compare_change",
        "authorized_amount",
    }:
        requires_confirmation = True
        reason = (
            "A palavra “receita” normalmente indica entrada de recursos, mas, neste "
            "contexto, a pergunta parece se referir ao valor destinado ao programa."
        )
    elif requires_confirmation:
        reason = (
            f"“{entity_label}” pode representar um órgão, uma função orçamentária "
            "ou um conjunto de programas e ações."
        )

    return {
        "intent": intent_key,
        "intent_label": intent_data["label"],
        "technical_concept": intent_data["technical_concept"],
        "entity": entity_key,
        "entity_label": entity_label if entity_data else None,
        "normalized_query": normalized_query,
        "search_terms": entity_data["search_terms"] if entity_data else [query],
        "requires_confirmation": requires_confirmation,
        "confirmation_reason": reason,
        "available_in_corpus": intent_data.get("available_in_corpus", True),
        "requires_structured_values": intent_data.get("requires_structured_values", False),
    }
