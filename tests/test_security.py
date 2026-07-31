from loa_api.security import current_user


def test_authenticated_headers_are_normalized() -> None:
    user = current_user(
        email="Reporter@Example.com",
        encoded_name="Maria%20Silva",
        name_encoding="percent-encoded-utf-8",
    )
    assert user.email == "reporter@example.com"
    assert user.full_name == "Maria Silva"
