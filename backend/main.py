"""FastAPI backend — LCC API proxy with OAuth2 authentication + Incident Notifier."""

import asyncio
import logging

logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException, Request, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx

from backend import lcc_client as lcc
from backend import opcua_client as opcua
from backend import device_cache as dc
import logging

logger = logging.getLogger(__name__)
from backend.notifier.api import router as notifier_router

log = logging.getLogger("lcc_tools.main")

app = FastAPI(title="LCC Tools")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Notifier API ──────────────────────────────────────────────────

app.include_router(notifier_router)


# ── Device health check (background) ───────────────────────────────

async def _device_health_check():
    """Periodically check if cached devices respond on OPC UA."""
    while True:
        await asyncio.sleep(1800)  # check every 30 minutes
        devices = dc.get_cached_devices()
        if not devices:
            continue
        client = await opcua.get_client()
        if not client:
            continue
        for dev in devices:
            try:
                node = client.get_node(dev["nodeId"])
                await node.read_browse_name()
                dc.set_device_online(dev["nodeId"])
            except Exception:
                dc.set_device_offline(dev["nodeId"])


# ── Notifier background task ───────────────────────────────────────

@app.on_event("startup")
async def start_notifier():
    """Launch the incident notifier poll loop as a background task."""
    asyncio.create_task(_device_health_check())
    try:
        from backend.notifier.service import Service

        config_path = "config/config.yaml"
        service = Service(config_path)
        asyncio.create_task(service.run())
        log.info("Incident Notifier background task started")
    except Exception:
        log.exception("Failed to start Incident Notifier (non-fatal)")


# ── Error handler ─────────────────────────────────────────────────

@app.exception_handler(httpx.HTTPStatusError)
async def http_error_handler(request: Request, exc: httpx.HTTPStatusError):
    detail = exc.response.text
    try:
        detail = exc.response.json()
    except Exception:
        pass
    return JSONResponse(status_code=exc.response.status_code, content={"error": detail})


@app.get("/api/health")
async def health():
    return {"status": "ok", "mode": "live"}


# ── Rooms ─────────────────────────────────────────────────────────

@app.get("/api/rooms")
async def list_rooms():
    return await lcc.get_rooms()


@app.post("/api/rooms", status_code=201)
async def create_room(body: dict):
    return await lcc.create_room(body)


@app.get("/api/rooms/detail")
async def get_room(roomId: str = Query(...)):
    return await lcc.get_room(roomId)


@app.delete("/api/rooms/detail")
async def delete_room(roomId: str = Query(...)):
    return await lcc.delete_room(roomId)


@app.patch("/api/rooms/detail")
async def patch_room(roomId: str = Query(...), body: dict = None):
    return await lcc.patch_room_meta(roomId, body or {})


# ── Discovery / Servers ───────────────────────────────────────────

@app.get("/api/discovery/servers")
async def list_servers():
    return await lcc.get_servers()


@app.post("/api/discovery/servers")
async def add_server(body: dict):
    return await lcc.create_server(body)


@app.delete("/api/discovery/servers/{server_id}")
async def delete_server(server_id: str):
    return await lcc.delete_server(server_id)


@app.get("/api/discovery/servers/{server_id}/credentials")
async def get_credentials(server_id: str):
    return await lcc.get_credentials(server_id)


@app.put("/api/discovery/servers/{server_id}/credentials")
async def put_credentials(server_id: str, body: dict):
    return await lcc.put_credentials(server_id, body)


@app.delete("/api/discovery/servers/{server_id}/credentials")
async def delete_credentials(server_id: str):
    return await lcc.delete_credentials(server_id)


# ── OPC UA Device Cache ─────────────────────────────────────────

@app.get("/api/opcua/devices/cached")
async def get_cached_devices():
    """Return cached device list (instant load)."""
    return {"devices": dc.get_cached_devices()}


@app.post("/api/opcua/devices/status")
async def check_device_status():
    """Run a device health check now."""
    devices = dc.get_cached_devices()
    if not devices:
        return {"checked": 0}
    client = await opcua.get_client()
    if not client:
        raise HTTPException(503, "OPC UA not connected")
    online = 0
    offline = 0
    for dev in devices:
        try:
            node = client.get_node(dev["nodeId"])
            await node.read_browse_name()
            dc.set_device_online(dev["nodeId"])
            online += 1
        except Exception:
            dc.set_device_offline(dev["nodeId"])
            offline += 1
    return {"checked": len(devices), "online": online, "offline": offline}


@app.post("/api/opcua/devices/refresh")
async def refresh_device_cache():
    """Fetch fresh device list from OPC UA, merge with persisted cache.
    Devices in cache but not in live list are marked offline."""
    try:
        data = await opcua.browse_node("ns=3;i=5001")
        live_devices = []
        live_serials = set()
        seen = set()
        for dev in data.get("children", []):
            name = dev.get("name", "?")
            if name in ("DeviceFeatures", "HA Configuration"):
                continue
            if name in seen:
                continue
            seen.add(name)
            serial = dev.get("nodeId", name)
            live_serials.add(serial)
            live_devices.append({
                "name": name,
                "nodeId": serial,
                "componentName": dev.get("componentName", ""),
            })

        # Update/add live devices, preserving componentNames
        dc.set_cached_devices(live_devices)

        # Mark devices NOT in the live list as offline
        all_cached = dc.get_cached_devices()
        for cached in all_cached:
            if cached["nodeId"] not in live_serials and cached["online"] != 0:
                dc.set_device_offline(cached["nodeId"])

        return {"devices": dc.get_cached_devices(), "cached": True, "count": len(live_devices)}
    except Exception as e:
        logger.error(f"Device refresh failed: {e}")
        raise HTTPException(500, str(e))


# ── Sensor History (LADS API) ───────────────────────────────────

from backend.auth import get_token as _get_token
from backend.lcc_client import LCC_BASE as _LCC_BASE
import httpx as _httpx

_LADS_HEADERS = {"Host": "lcc.ieu.local"}

async def _lads_get(path: str, **params):
    token = await _get_token()
    headers = {**_LADS_HEADERS, "Authorization": f"Bearer {token}"}
    async with _httpx.AsyncClient(verify=False) as client:
        r = await client.get(f"{_LCC_BASE}{path}", headers=headers, params=params, timeout=30)
        return r.json()


@app.get("/api/lads/devices")
async def lads_devices(location: str = None):
    params = {}
    if location:
        params["hierarchicalLocation"] = location
    return await _lads_get("/lads/DeviceSet", **params)


@app.get("/api/lads/devices/{device_id}/units")
async def lads_functional_units(device_id: str):
    return await _lads_get(f"/lads/DeviceSet/{device_id}/FunctionalUnitSet")


@app.get("/api/lads/devices/{device_id}/units/{unit_id}/functions")
async def lads_functions(device_id: str, unit_id: str):
    return await _lads_get(f"/lads/DeviceSet/{device_id}/FunctionalUnitSet/{unit_id}/FunctionSet")


@app.get("/api/lads/devices/{device_id}/units/{unit_id}/functions/{function_id}/history")
async def lads_history(
    device_id: str, unit_id: str, function_id: str,
    startTime: str, endTime: str = None,
    numValuesPerNode: int = 50000,
):
    params = {"startTime": startTime, "numValuesPerNode": numValuesPerNode}
    if endTime:
        params["endTime"] = endTime
    return await _lads_get(
        f"/lads/history/{device_id}/FunctionalUnitSet/{unit_id}/FunctionSet/{function_id}/values",
        **params
    )


# ── OPC UA Status ──────────────────────────────────────────────

@app.get("/api/opcua/status")
async def opcua_status():
    try:
        client = await opcua.get_client()
        node = client.get_objects_node()
        await node.get_children()
        return {"connected": True, "url": opcua.OPC_URL}
    except Exception as e:
        return {"connected": False, "url": opcua.OPC_URL, "error": str(e)[:100]}


# ── OPC UA Browser ────────────────────────────────────────────────

@app.get("/api/opcua/browse")
async def browse_opcua(nodeId: str | None = None):
    return await opcua.browse_node(nodeId)


@app.get("/api/opcua/read")
async def read_opcua(nodeId: str):
    return await opcua.read_node_value(nodeId)


@app.post("/api/opcua/write")
async def write_opcua(body: dict):
    return await opcua.write_node_value(body["nodeId"], body["value"])


# ── MQTT Explorer ──────────────────────────────────────────────────

from backend import mqtt_explorer as mqtt_exp


@app.get("/api/mqtt/state")
async def mqtt_state():
    return mqtt_exp.get_state()


@app.post("/api/mqtt/connect")
async def mqtt_connect(body: dict):
    host = body.get("host", "")
    port = body.get("port", 8883)
    if not host:
        raise HTTPException(400, "host required")
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, mqtt_exp.connect, host, port)
    return result


@app.post("/api/mqtt/disconnect")
async def mqtt_disconnect():
    return mqtt_exp.disconnect()


@app.get("/api/mqtt/topics")
async def mqtt_topics():
    return {"topics": mqtt_exp.get_topics()}


@app.get("/api/mqtt/messages")
async def mqtt_messages(topic: str = None, limit: int = 50):
    return {"messages": mqtt_exp.get_messages(topic, limit)}


@app.post("/api/mqtt/publish")
async def mqtt_publish(body: dict):
    topic = body.get("topic", "")
    payload = body.get("payload", "")
    if not topic:
        raise HTTPException(400, "topic required")
    retain = body.get("retain", True)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, mqtt_exp.publish, topic, payload, 1, retain)
    return result


@app.websocket("/api/mqtt/ws")
async def mqtt_websocket(ws: WebSocket):
    await ws.accept()
    last_msg_count = 0
    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
            msgs = mqtt_exp.get_messages()
            if len(msgs) > last_msg_count:
                new_msgs = msgs[last_msg_count:]
                last_msg_count = len(msgs)
                await ws.send_json({"new_messages": new_msgs})
            await asyncio.sleep(0.5)
    except Exception:
        pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8701, reload=True)
