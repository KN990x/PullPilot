from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from server.auth_policy import (
    PASSWORD_MAX_LEN,
    PASSWORD_MIN_LEN,
    USERNAME_MAX_LEN,
    USERNAME_MIN_LEN,
    USERNAME_PATTERN,
)

CronFrequency = Literal["daily", "weekly", "monthly"]
TaskType = Literal["cron", "date"]


class SetupInput(BaseModel):
    username: str = Field(
        ...,
        min_length=USERNAME_MIN_LEN,
        max_length=USERNAME_MAX_LEN,
        pattern=USERNAME_PATTERN,
    )
    password: str = Field(..., min_length=PASSWORD_MIN_LEN, max_length=PASSWORD_MAX_LEN)
    password_confirm: str = Field(..., min_length=PASSWORD_MIN_LEN, max_length=PASSWORD_MAX_LEN)

    @model_validator(mode="after")
    def passwords_must_match(self) -> Self:
        if self.password != self.password_confirm:
            raise ValueError("Las contraseñas no coinciden")
        return self


class LoginInput(BaseModel):
    username: str = Field(..., max_length=USERNAME_MAX_LEN)
    password: str = Field(..., max_length=PASSWORD_MAX_LEN)


class CredentialsInput(BaseModel):
    current_password: str = Field(..., max_length=PASSWORD_MAX_LEN)
    username: str | None = Field(
        default=None,
        min_length=USERNAME_MIN_LEN,
        max_length=USERNAME_MAX_LEN,
        pattern=USERNAME_PATTERN,
    )
    new_password: str | None = Field(
        default=None, min_length=PASSWORD_MIN_LEN, max_length=PASSWORD_MAX_LEN
    )
    new_password_confirm: str | None = Field(
        default=None, min_length=PASSWORD_MIN_LEN, max_length=PASSWORD_MAX_LEN
    )

    @model_validator(mode="after")
    def check_change(self) -> Self:
        if self.new_password is not None and self.new_password != self.new_password_confirm:
            raise ValueError("Las contraseñas nuevas no coinciden")
        if self.username is None and self.new_password is None:
            raise ValueError("No hay nada que cambiar")
        return self


class AuthStatusOut(BaseModel):
    setup_complete: bool
    authenticated: bool
    auth_enabled: bool
    username: str | None = None


class AuthResultOut(BaseModel):
    status: Literal["ok"] = "ok"
    username: str


class Project(BaseModel):
    name: str
    path: str
    status: str
    containers: int
    excluded: bool
    full_stop: bool


class ScheduleInput(BaseModel):
    target: str = Field(
        ...,
        max_length=256,
        pattern=r"^(GLOBAL|[^\s/\\]+)$",
    )
    task_type: TaskType = "cron"
    frequency: CronFrequency = "daily"
    week_day: str = Field(default="*", pattern=r"^(\*|mon|tue|wed|thu|fri|sat|sun)$")
    day_of_month: str = Field(default="1", pattern=r"^(?:[1-9]|[12]\d|3[01])$")
    hour: int = Field(default=0, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    date_iso: str | None = None

    @model_validator(mode="after")
    def require_date_iso_for_once(self) -> Self:
        if self.task_type == "date":
            if not (self.date_iso and str(self.date_iso).strip()):
                raise ValueError("date_iso es obligatorio para task_type date")
        return self


class ScheduledTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    target: str
    task_type: str
    expression: str
    active: bool


class UpdateLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    status: str
    summary: str
    details: str
