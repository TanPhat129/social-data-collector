from enum import StrEnum

from pydantic import BaseModel, Field

from app.schemas import Source


class AccountStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    IN_USE = "IN_USE"
    NEEDS_MANUAL_ACTION = "NEEDS_MANUAL_ACTION"
    DISABLED = "DISABLED"


class ManagedAccount(BaseModel):
    id: str
    facebook_uid: str
    profile_path: str
    status: AccountStatus = AccountStatus.AVAILABLE
    enabled: bool = True


class AccountPool(BaseModel):
    id: str
    account_ids: list[str] = Field(min_length=1)
    max_concurrent_accounts: int = Field(default=10, ge=1)


class SourceAssignment(BaseModel):
    pool_id: str
    account_id: str
    source_id: str
    shard: int = Field(ge=1)
    priority: int = 100
    enabled: bool = True
    backup: bool = False


class OrchestrationDocument(BaseModel):
    accounts: list[ManagedAccount]
    pools: list[AccountPool]
    sources: list[Source]
    assignments: list[SourceAssignment]
    shard_pause_seconds: int = Field(default=45, ge=30, le=60)
    account_shard_timeout_seconds: int = Field(default=900, ge=60)
