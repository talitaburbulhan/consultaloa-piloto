from dataclasses import dataclass
from urllib.parse import unquote

import jwt
from fastapi import Header, HTTPException

from .config import get_settings


@dataclass(frozen=True)
class CurrentUser:
    email: str
    full_name: str | None
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
    if settings.cloudflare_access_team_domain or settings.cloudflare_access_audience:
        if not (
            settings.cloudflare_access_team_domain
            and settings.cloudflare_access_audience
        ):
            raise HTTPException(500, "Configuração incompleta do Cloudflare Access")
        if not cloudflare_assertion:
            raise HTTPException(401, "Autenticação Cloudflare Access obrigatória")
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
        encoded_name = None
        name_encoding = None
    if not email:
        if settings.auth_required:
            raise HTTPException(401, "Autenticação interna obrigatória")
        email = "desenvolvimento@local"
    normalized = email.strip().casefold()
    allowed = settings.allowed_editors
    if settings.auth_required and allowed and normalized not in allowed:
        raise HTTPException(403, "Usuário sem autorização editorial")
    full_name = (
        unquote(encoded_name)
        if encoded_name and name_encoding == "percent-encoded-utf-8"
        else None
    )
    return CurrentUser(
        email=normalized,
        full_name=full_name,
        is_editor=not allowed or normalized in allowed,
        is_reviewer=not settings.auth_required or normalized in settings.allowed_reviewers,
    )
