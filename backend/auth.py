"""OAuth2 client credentials flow for LCC API."""

import time
import os
import httpx

# LCC API config
LCC_HOST = os.getenv("LCC_HOST", "10.89.11.52")
LCC_TOKEN_URL = f"https://{LCC_HOST}/oauth/token"
LCC_CLIENT_ID = os.getenv("LCC_CLIENT_ID", "iuta-notification")
LCC_CLIENT_SECRET = os.getenv("LCC_CLIENT_SECRET", "YF72ojKY99U")
LCC_SCOPE = "openid audience:server:client_id:lcc-api"

# Token cache
_token: dict | None = None
_token_expires_at: float = 0


async def get_token() -> str:
    """Get a valid OAuth2 access token, refreshing if expired."""
    global _token, _token_expires_at

    if _token and time.time() < _token_expires_at - 60:
        return _token["access_token"]

    async with httpx.AsyncClient(verify=False) as client:
        resp = await client.post(
            LCC_TOKEN_URL,
            headers={
                "Host": "lcc.ieu.local",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "client_credentials",
                "client_id": LCC_CLIENT_ID,
                "client_secret": LCC_CLIENT_SECRET,
                "scope": LCC_SCOPE,
            },
            timeout=15,
        )
        resp.raise_for_status()
        _token = resp.json()
        _token_expires_at = time.time() + _token.get("expires_in", 3600)
        return _token["access_token"]
