"""LCC API HTTP client using OAuth2 tokens."""

import os
import httpx
from urllib.parse import quote
from backend.auth import get_token

LCC_HOST = os.getenv("LCC_HOST", "10.89.11.52")
LCC_BASE = f"https://{LCC_HOST}/api/v2"


async def _request(method: str, path: str, **kwargs) -> dict:
    """Make an authenticated request to the LCC API."""
    token = await get_token()
    async with httpx.AsyncClient(verify=False, timeout=30) as client:
        resp = await client.request(
            method,
            f"{LCC_BASE}{path}",
            headers={
                "Host": "lcc.ieu.local",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            **kwargs,
        )
        resp.raise_for_status()
        if resp.status_code == 204:
            return {"deleted": True}
        return resp.json()


# ── Rooms (roomIds contain slashes → URL-encode) ────────────────

def _enc(path: str) -> str:
    """URL-encode room IDs in path segments."""
    return path  # httpx handles encoding; we pass raw paths with %2F


async def get_rooms():
    return await _request("GET", "/rooms")


async def get_room(room_id: str):
    return await _request("GET", f"/rooms/{quote(room_id, safe='')}")


async def create_room(data: dict):
    return await _request("POST", "/rooms", json=data)


async def delete_room(room_id: str):
    return await _request("DELETE", f"/rooms/{quote(room_id, safe='')}")


async def patch_room_meta(room_id: str, data: dict):
    return await _request("PATCH", f"/rooms/{quote(room_id, safe='')}/meta", json=data)


# ── Discovery / Servers ─────────────────────────────────────────

async def get_servers():
    return await _request("GET", "/discovery/servers")


async def create_server(data: dict):
    return await _request("POST", "/discovery/servers", json=data)


async def delete_server(server_id: str):
    return await _request("DELETE", f"/discovery/servers/{server_id}")


async def get_credentials(server_id: str):
    return await _request("GET", f"/discovery/servers/{server_id}/credentials")


async def put_credentials(server_id: str, data: dict):
    return await _request("PUT", f"/discovery/servers/{server_id}/credentials", json=data)


async def delete_credentials(server_id: str):
    return await _request("DELETE", f"/discovery/servers/{server_id}/credentials")
