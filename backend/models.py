"""Pydantic models matching LCC API schemas."""

from pydantic import BaseModel, Field
from typing import Optional


# ── Room ────────────────────────────────────────────────────────

class RoomContact(BaseModel):
    name: str = ""
    email: str = ""
    details: str = ""


class RoomAirflow(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None


class RoomMonitoring(BaseModel):
    name: Optional[str] = None
    path: str


class RoomCreateInput(BaseModel):
    roomId: str
    name: str
    number: Optional[str] = None
    contact: Optional[RoomContact] = None


class RoomMetaInput(BaseModel):
    contact: Optional[RoomContact] = None
    number: Optional[str] = None
    name: Optional[str] = None
    monitoring: Optional[list[RoomMonitoring]] = None
    airflow: Optional[RoomAirflow] = None


class Room(BaseModel):
    roomId: str
    name: str
    number: Optional[str] = None
    contact: Optional[RoomContact] = None
    airflow: Optional[RoomAirflow] = None
    monitoring: list[RoomMonitoring] = []


class RoomResponse(BaseModel):
    data: Room


class RoomListResponse(BaseModel):
    data: list[Room]
    meta: dict = {"total": 0, "page": 1, "perPage": 50}


# ── Discovery / OPC UA Servers ──────────────────────────────────

class DiscoveredServer(BaseModel):
    serverId: str
    endpointUrl: str
    name: Optional[str] = None
    serverType: str = "discovered"
    online: bool = True
    hasCredentials: bool = False


class ManualServerInput(BaseModel):
    endpointUrl: str
    name: Optional[str] = None
    serverId: Optional[str] = None


class CredentialsMetaResponse(BaseModel):
    serverId: str
    authType: Optional[str] = None
    username: Optional[str] = None
    hasPassword: bool = False


class CredentialsInput(BaseModel):
    authType: str  # anonymous, username, certificate
    username: Optional[str] = None
    password: Optional[str] = None


# ── Generic ─────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    error: str


class DeleteResponse(BaseModel):
    deleted: bool = True
