from loa_api.editorial import ambiguity_warnings


def test_bare_four_digit_number_is_ambiguous() -> None:
    warnings = ambiguity_warnings("Quanto foi destinado à ação 2024?")
    assert warnings
    assert "código" in warnings[0]


def test_explicit_loa_year_is_not_ambiguous() -> None:
    assert ambiguity_warnings("Quanto foi destinado na LOA 2024?") == []


def test_execution_question_is_flagged() -> None:
    warnings = ambiguity_warnings("Quanto foi efetivamente pago?")
    assert any("execução" in warning for warning in warnings)
