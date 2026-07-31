from loa_api.chunking import cosine, embed, normalize, split_chunks


def test_normalization_preserves_searchability() -> None:
    assert normalize("Saúde  Pública") == "saude publica"


def test_chunks_keep_all_text() -> None:
    text = "A" * 3000
    chunks = split_chunks(text, target_chars=500)
    assert "".join(chunks) == text


def test_related_vectors_score_above_unrelated_vectors() -> None:
    query = embed("orçamento da saúde")
    assert cosine(query, embed("saúde no orçamento federal")) > cosine(
        query, embed("defesa e forças armadas")
    )
