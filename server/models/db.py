import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from server.database import Base

AUTH_ROW_ID = 1


class AuthCredential(Base):
    __tablename__ = "auth_credentials"

    # El singleton se garantiza en el motor y no en la aplicación: dos peticiones
    # simultáneas al asistente chocan contra la clave primaria y la segunda recibe
    # IntegrityError, sin ventana entre el SELECT y el INSERT.
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_auth_credentials_singleton"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Se incrementa en cada cambio de credenciales: las cookies emitidas antes dejan de
    # validar, o sea que cambiar la contraseña cierra la sesión en el resto de equipos.
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.UTC),
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.UTC),
        onupdate=lambda: datetime.datetime.now(datetime.UTC),
    )


class ProjectSettings(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    path: Mapped[str] = mapped_column(String)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    full_stop: Mapped[bool] = mapped_column(Boolean, default=False)


class ScheduledTask(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    target: Mapped[str] = mapped_column(String)
    task_type: Mapped[str] = mapped_column(String)
    expression: Mapped[str] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class UpdateLog(Base):
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.UTC),
    )
    status: Mapped[str] = mapped_column(String)
    summary: Mapped[str] = mapped_column(Text)
    details: Mapped[str] = mapped_column(Text)
