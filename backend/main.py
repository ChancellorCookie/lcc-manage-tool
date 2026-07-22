"""FastAPI backend — LCC API proxy with OAuth2 authentication."""

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx

from backend import lcc_client as lcc
from backend import opcua_client as opcua
from backend import device_cache as dc

app = FastAPI(title="LCC Manage Tool")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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


# ── Rooms ───────────────────────────────────────────────────────
# Room IDs contain slashes (e.g. IEU/R406), so we use query params for single-room ops.

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


# ── Discovery / Servers ─────────────────────────────────────────

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


# ── OPC UA Browser ──────────────────────────────────────────────

@app.get("/api/opcua/browse")
async def browse_opcua(nodeId: str | None = None):
    return await opcua.browse_node(nodeId)


@app.get("/api/opcua/read")
async def read_opcua(nodeId: str):
    return await opcua.read_node_value(nodeId)


@app.post("/api/opcua/write")
async def write_opcua(body: dict):
    return await opcua.write_node_value(body["nodeId"], body["value"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8701, reload=True)
