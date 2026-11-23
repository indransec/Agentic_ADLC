"""``/auth/*`` endpoints (contracts/platform-api.openapi.yaml; 022 contracts/session.md).

Sign-in gives a bearer token by default (tools, tests, pilot processes: unchanged). With
``"session": "cookie"`` (the browser application) it instead sets the HttpOnly, SameSite=Strict
cookie ``adlc_session`` and answers the session's CSRF value, never the token, so page scripts
cannot read the session (FR-013).
"""

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from adlc.api.auth import (
    CROSS_SITE,
    CSRF_HEADER,
    SESSION_COOKIE,
    SIGN_IN_CSRF,
    csrf_value,
    current_person,
    is_https,
)
from adlc.identity.protocol import IdentityProvider, InvalidCredentials, Person

router = APIRouter(prefix="/auth")


class SignInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_name: str = Field(min_length=1, max_length=40)
    password: SecretStr = Field(min_length=1)
    # 022: "cookie" for the browser application; the default keeps every existing client as is
    session: Literal["bearer", "cookie"] = "bearer"


class PersonOut(BaseModel):
    account_name: str
    display_name: str
    roles: list[str]

    @classmethod
    def of(cls, person: Person) -> "PersonOut":
        return cls(
            account_name=person.account_name,
            display_name=person.display_name,
            roles=sorted(person.roles),
        )


class MeOut(PersonOut):
    """The signed-in person; with the session's CSRF value when the session is the cookie."""

    csrf_token: str | None = None


class SignInResponse(BaseModel):
    token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105  # scheme name, not a secret
    expires_at: datetime
    person: PersonOut


class BrowserSignInResponse(BaseModel):
    """Cookie-mode sign-in: the token went into the HttpOnly cookie, not here."""

    expires_at: datetime
    person: PersonOut
    csrf_token: str


def _provider(request: Request) -> IdentityProvider:
    provider: IdentityProvider = request.app.state.identity
    return provider


@router.post("/sign-in", response_model=SignInResponse | BrowserSignInResponse)
def sign_in(
    body: SignInRequest,
    request: Request,
    provider: Annotated[IdentityProvider, Depends(_provider)],
) -> SignInResponse | BrowserSignInResponse | JSONResponse:
    if body.session == "cookie" and request.headers.get(CSRF_HEADER) != SIGN_IN_CSRF:
        return JSONResponse(CROSS_SITE, status_code=403)  # a form from another site (login CSRF)
    try:
        grant = provider.sign_in(body.account_name, body.password)
    except InvalidCredentials:
        return JSONResponse(
            {"kind": "not_signed_in", "detail": "invalid credentials"}, status_code=401
        )
    person = PersonOut.of(grant.person)
    if body.session == "bearer":
        return SignInResponse(token=grant.token, expires_at=grant.expires_at, person=person)
    answer = BrowserSignInResponse(
        expires_at=grant.expires_at,
        person=person,
        csrf_token=csrf_value(request.app.state.csrf_secret, grant.token),
    )
    response = JSONResponse(answer.model_dump(mode="json"))
    seconds = max(0, int((grant.expires_at - datetime.now(UTC)).total_seconds()))
    response.set_cookie(
        SESSION_COOKIE,
        grant.token,
        max_age=seconds,
        path="/",
        httponly=True,
        samesite="strict",
        secure=is_https(request),
    )
    return response


@router.post("/sign-out", status_code=204)
def sign_out(
    request: Request, provider: Annotated[IdentityProvider, Depends(_provider)]
) -> Response:
    provider.sign_out(request.state.token)
    response = Response(status_code=204)
    if request.state.session_via == "cookie":
        response.delete_cookie(
            SESSION_COOKIE, path="/", httponly=True, samesite="strict", secure=is_https(request)
        )
    return response


@router.get("/me", response_model=MeOut, response_model_exclude_unset=True)
def me(request: Request, person: Annotated[Person, Depends(current_person)]) -> MeOut:
    out = MeOut.model_validate(PersonOut.of(person).model_dump())
    if request.state.session_via == "cookie":
        out.csrf_token = csrf_value(request.app.state.csrf_secret, request.state.token)
    return out
