from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from loa_api.security import CurrentUser, current_user, reviewer_user


def test_authenticated_headers_are_normalized() -> None:
    user = current_user(
        email="Reporter@Example.com",
        encoded_name="Maria%20Silva",
        name_encoding="percent-encoded-utf-8",
    )
    assert user.email == "reporter@example.com"
    assert user.full_name == "Maria Silva"
    assert user.authenticated


def test_public_production_request_is_anonymous_and_not_reviewer(monkeypatch) -> None:
    settings = SimpleNamespace(
        environment="production",
        auth_required=False,
        cloudflare_access_team_domain="https://team.cloudflareaccess.com",
        cloudflare_access_audience="audience",
        allowed_editors={"editor@example.com"},
        allowed_reviewers={"reviewer@example.com"},
    )
    monkeypatch.setattr("loa_api.security.get_settings", lambda: settings)

    user = current_user(
        email="reviewer@example.com",
        encoded_name=None,
        name_encoding=None,
        cloudflare_assertion=None,
    )

    assert user.email == "publico@anonimo"
    assert not user.authenticated
    assert not user.is_editor
    assert not user.is_reviewer


def test_anonymous_user_cannot_download_feedback_report() -> None:
    user = CurrentUser(
        email="publico@anonimo",
        full_name=None,
        authenticated=False,
        is_editor=False,
        is_reviewer=False,
    )

    with pytest.raises(HTTPException) as error:
        reviewer_user(user)

    assert error.value.status_code == 401


def test_authenticated_authorized_reviewer_can_download_report() -> None:
    user = CurrentUser(
        email="reviewer@example.com",
        full_name=None,
        authenticated=True,
        is_editor=False,
        is_reviewer=True,
    )

    assert reviewer_user(user) is user
