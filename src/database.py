import logging
from typing import Any, Optional, Type

from sqlalchemy import (
    ColumnExpressionArgument,
    Integer,
    ScalarResult,
    String,
    create_engine,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


# https://github.com/glauth/glauth-postgres/blob/main/postgres.go
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, name="name", unique=True)
    uid_number: Mapped[int] = mapped_column(name="uidnumber")
    gid_number: Mapped[int] = mapped_column(name="primarygroup")
    password_sha256: Mapped[Optional[str]] = mapped_column(name="passsha256")
    password_bcrypt: Mapped[Optional[str]] = mapped_column(name="passbcrypt")


class Group(Base):
    __tablename__ = "ldapgroups"

    id = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(name="name", unique=True)
    gid_number: Mapped[int] = mapped_column(name="gidnumber")


class Capability(Base):
    __tablename__ = "capabilities"

    id = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(name="userid")
    action: Mapped[str] = mapped_column(default="search")
    object: Mapped[str] = mapped_column(default="*")


class Operation:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def __enter__(self) -> "Operation":
        engine = create_engine(self._dsn)
        self._session = Session(engine)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type:
            logger.error(
                f"The database operation failed. The exception " f"{exc_type} raised: {exc_val}"
            )
            self._session.rollback()
        else:
            self._session.commit()

        self._session.close()

    def select(
        self, table: Type[Base], *criteria: ColumnExpressionArgument
    ) -> Optional[ScalarResult]:
        return self._session.scalars(select(table).filter(*criteria)).first()

    def add(self, entity: Base) -> None:
        self._session.add(entity)
