from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    nom: str
    password_hash: str
    cree_le: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Client(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    nom: str = Field(index=True)
    email: str | None = None
    telephone: str | None = None
    cree_le: datetime = Field(default_factory=lambda: datetime.now(UTC))
