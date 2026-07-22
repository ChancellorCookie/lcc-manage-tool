"""Mock data store for LCC backend."""

from backend.models import (
    Room, RoomContact, RoomAirflow, RoomMonitoring,
    DiscoveredServer, CredentialsMetaResponse,
)


# ── Rooms ───────────────────────────────────────────────────────

_rooms: dict[str, Room] = {
    "entwicklungslabor": Room(
        roomId="entwicklungslabor",
        name="Entwicklungslabor",
        number="A-101",
        contact=RoomContact(name="Moriz Walter", email="moriz.walter@waldner.de", details="T.345"),
        airflow=RoomAirflow(min=1200, max=2400),
        monitoring=[
            RoomMonitoring(name="Room Temp", path="DeviceSet/SP2DC800200/FunctionalUnitSet/SP2DC800200/FunctionSet/1"),
            RoomMonitoring(path="DeviceSet/SP2DC800200/FunctionalUnitSet/SP2DC800200/FunctionSet/2"),
        ],
    ),
    "office-essentim": Room(
        roomId="office-essentim",
        name="Office Essentim",
        number="B-201",
        contact=RoomContact(name="Bruno Schliersmair", email="bruno@essentim.com", details="Großraum"),
        airflow=RoomAirflow(min=800, max=1800),
        monitoring=[
            RoomMonitoring(name="Room Temp", path="DeviceSet/SP2DC800200/FunctionalUnitSet/SP2DC800200/FunctionSet/1"),
        ],
    ),
    "chemielabor": Room(
        roomId="chemielabor",
        name="Chemielabor",
        number="C-305",
        contact=RoomContact(name="Dr. Anna Schmidt", email="anna.schmidt@waldner.de", details="Abzug 1-4"),
        airflow=RoomAirflow(min=2000, max=4000),
        monitoring=[
            RoomMonitoring(name="Abzug 1", path="DeviceSet/S1-1016939/FunctionalUnitSet/Fumehood/FunctionSet/Airflow"),
            RoomMonitoring(name="Abzug 2", path="DeviceSet/S1-1016940/FunctionalUnitSet/Fumehood/FunctionSet/Airflow"),
            RoomMonitoring(name="Room Temp", path="DeviceSet/S1-1016939/FunctionalUnitSet/SensorPanel/FunctionSet/1"),
        ],
    ),
}


# ── OPC UA Servers ──────────────────────────────────────────────

_servers: dict[str, DiscoveredServer] = {
    "srv-001": DiscoveredServer(
        serverId="srv-001",
        endpointUrl="opc.tcp://192.168.10.11:4840",
        name="LabController EG",
        serverType="discovered",
        online=True,
        hasCredentials=False,
    ),
    "srv-002": DiscoveredServer(
        serverId="srv-002",
        endpointUrl="opc.tcp://192.168.10.12:4840",
        name="LabController OG",
        serverType="discovered",
        online=True,
        hasCredentials=True,
    ),
    "srv-manual-1": DiscoveredServer(
        serverId="srv-manual-1",
        endpointUrl="opc.tcp://10.0.1.50:4840",
        name="Außenstation",
        serverType="manual",
        online=True,
        hasCredentials=False,
    ),
}

_credentials: dict[str, CredentialsMetaResponse] = {
    "srv-002": CredentialsMetaResponse(
        serverId="srv-002",
        authType="username",
        username="operator",
        hasPassword=True,
    ),
}


# ── Accessors ───────────────────────────────────────────────────

def get_rooms() -> list[Room]:
    return list(_rooms.values())


def get_room(room_id: str) -> Room | None:
    return _rooms.get(room_id)


def create_room(room_id: str, name: str, number: str | None = None,
                contact: RoomContact | None = None) -> Room:
    r = Room(roomId=room_id, name=name, number=number, contact=contact or RoomContact())
    _rooms[room_id] = r
    return r


def update_room(room_id: str, updates: dict) -> Room | None:
    r = _rooms.get(room_id)
    if not r:
        return None
    for key, val in updates.items():
        if val is not None and hasattr(r, key):
            setattr(r, key, val)
    return r


def delete_room(room_id: str) -> bool:
    if room_id in _rooms:
        del _rooms[room_id]
        return True
    return False


def get_servers() -> list[DiscoveredServer]:
    return list(_servers.values())


def create_server(server: DiscoveredServer) -> DiscoveredServer:
    _servers[server.serverId] = server
    return server


def delete_server(server_id: str) -> bool:
    if server_id in _servers:
        del _servers[server_id]
        _credentials.pop(server_id, None)
        return True
    return False


def get_credentials(server_id: str) -> CredentialsMetaResponse | None:
    return _credentials.get(server_id)


def put_credentials(server_id: str, auth_type: str,
                    username: str | None = None,
                    password: str | None = None) -> CredentialsMetaResponse:
    cred = CredentialsMetaResponse(
        serverId=server_id,
        authType=auth_type,
        username=username,
        hasPassword=bool(password),
    )
    _credentials[server_id] = cred
    return cred


def delete_credentials(server_id: str) -> bool:
    if server_id in _credentials:
        del _credentials[server_id]
        return True
    return False
