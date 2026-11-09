"""``/auth/*`` endpoints (contracts/platform-api.openapi.yaml)."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from adlc.api.auth import current_person
from adlc.identity.protocol import IdentityProvider, InvalidCredentials, Person

router = APIRouter(prefix="/auth")


class SignInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_name: str = Field(min_length=1, max_length=40)
    password: SecretStr = Field(min_length=1)


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


class SignInResponse(BaseModel):
    token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105  # scheme name, not a secret
    expires_at: datetime
    person: PersonOut


def _provider(request: Request) -> IdentityProvider:
    provider: IdentityProvider = request.app.state.identity
    return provider


@router.post("/sign-in", response_model=SignInResponse)
def sign_in(
    body: SignInRequest, provider: Annotated[IdentityProvider, Depends(_provider)]
) -> SignInResponse | JSONResponse:
    try:
        grant = provider.sign_in(body.account_name, body.password)
    except InvalidCredentials:
        return JSONResponse({"detail": "invalid credentials"}, status_code=401)
    return SignInResponse(
        token=grant.token, expires_at=grant.expires_at, person=PersonOut.of(grant.person)
    )


@router.post("/sign-out", status_code=204)
def sign_out(
    request: Request, provider: Annotated[IdentityProvider, Depends(_provider)]
) -> Response:
    provider.sign_out(request.state.token)
    return Response(status_code=204)


@router.get("/me", response_model=PersonOut)
def me(person: Annotated[Person, Depends(current_person)]) -> PersonOut:
    return PersonOut.of(person)
