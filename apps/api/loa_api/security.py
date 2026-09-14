from dataclasses import dataclass
from urllib.parse import unquote

import jwt
from fastapi import Depends, Header, HTTPException

from .config import get_settings


@dataclass(frozen=True)
class CurrentUser:
    email: str
    full_name: str | None
    authenticated: bool
    is_editor: bool
    is_reviewer: bool


def current_user(
    email: str | None = Header(default=None, alias="oai-authenticated-user-email"),
    encoded_name: str | None = Header(default=None, alias="oai-authenticated-user-full-name"),
    name_encoding: str | None = Header(
        default=None, alias="oai-authenticated-user-full-name-encoding"
    ),
    cloudflare_assertion: str | None = Header(
        default=None, alias="cf-access-jwt-assertion"
    ),
) -> CurrentUser:
    settings = get_settings()
    email = email if isinstance(email, str) else None
    encoded_name = encoded_name if isinstance(encoded_name, str) else None
    name_encoding = name_encoding if isinstance(name_encoding, str) else None
    cloudflare_assertion = (
        cloudflare_assertion if isinstance(cloudflare_assertion, str) else None
    )
    access_configured = bool(
        settings.cloudflare_access_team_domain
        and settings.cloudflare_access_audience
    )
    if (
        settings.environment == "production"
        and settings.auth_required
        and not access_configured
    ):
        raise HTTPException(503, "Cloudflare Access ainda não foi configurado")
    authenticated = False
    if cloudflare_assertion:
        if not access_configured:
            raise HTTPException(500, "Configuração incompleta do Cloudflare Access")
        team_domain = settings.cloudflare_access_team_domain.rstrip("/")
        try:
            signing_key = jwt.PyJWKClient(
                f"{team_domain}/cdn-cgi/access/certs"
            ).get_signing_key_from_jwt(cloudflare_assertion)
            claims = jwt.decode(
                cloudflare_assertion,
                signing_key.key,
                algorithms=["RS256"],
                audience=settings.cloudflare_access_audience,
                issuer=team_domain,
            )
        except jwt.PyJWTError as error:
            raise HTTPException(401, "Token do Cloudflare Access inválido") from error
        email = claims.get("email")
        if not isinstance(email, str) or not email.strip():
            raise HTTPException(403, "Token sem e-mail de usuário")
        authenticated = True
        encoded_name = None
        name_encoding = None
    elif settings.auth_required:
        raise HTTPException(401, "Autenticação Cloudflare Access obrigatória")
    elif settings.environment == "production":
        # Never trust identity headers supplied directly by a public visitor.
        email = None
    elif email:
        authenticated = True
    if not email:
        email = "publico@anonimo"
    normalized = email.strip().casefold()
    allowed_editors = settings.allowed_editors
    allowed_reviewers = settings.allowed_reviewers
    allowed_users = allowed_editors | allowed_reviewers
    if settings.environment == "production" and settings.auth_required and not allowed_users:
        raise HTTPException(
            503, "A lista de usuários autorizados do piloto ainda não foi configurada"
        )
    if settings.auth_required and normalized not in allowed_users:
        raise HTTPException(403, "Usuário sem autorização para o piloto")
    full_name = (
        unquote(encoded_name)
        if encoded_name and name_encoding == "percent-encoded-utf-8"
        else None
    )
    return CurrentUser(
        email=normalized,
        full_name=full_name,
        authenticated=authenticated,
        is_editor=authenticated
        and (not allowed_editors or normalized in allowed_editors),
        is_reviewer=authenticated and normalized in allowed_reviewers,
    )


def reviewer_user(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    """Require a validated Access identity for editorial-only endpoints."""
    if not user.authenticated:
        raise HTTPException(401, "Autenticação da revisora obrigatória")
    if not user.is_reviewer:
        raise HTTPException(403, "Relatório disponível somente para a revisora responsável")
    return user
