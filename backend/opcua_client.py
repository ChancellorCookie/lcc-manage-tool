"""OPC-UA client wrapper using asyncua for the LCC proxy server."""

import asyncio
import os
from asyncua import Client

OPC_URL = os.getenv("OPC_URL", "opc.tcp://10.89.11.52:4840")

_client: Client | None = None
_lock = asyncio.Lock()


async def get_client() -> Client:
    """Get or create a connected OPC-UA client (singleton, auto-reconnect)."""
    global _client
    async with _lock:
        if _client is None:
            _client = Client(url=OPC_URL, timeout=30)
            await _client.connect()
        else:
            try:
                # Test connection by actually reading something
                await _client.get_objects_node().get_children()
            except Exception:
                try:
                    await _client.disconnect()
                except Exception:
                    pass
                _client = Client(url=OPC_URL, timeout=30)
                await _client.connect()
    return _client


async def browse_node(node_id: str | None = None) -> dict:
    """Browse a node and return its children with metadata."""
    client = await get_client()

    if node_id:
        # Parse ns;i or ns;s style node ids
        node = _parse_node(client, node_id)
    else:
        node = client.get_objects_node()

    try:
        browse_name = await node.read_browse_name()
        name = browse_name.Name
    except Exception:
        name = "Root"

    children = []
    for child in await node.get_children():
        try:
            bn = await child.read_browse_name()
            cn = bn.Name
        except Exception:
            cn = str(child.nodeid)

        cid = _node_to_str(child.nodeid)
        children.append({
            "name": cn,
            "nodeId": cid,
            "hasChildren": True,  # lazy-check on expand
        })

    return {
        "name": name,
        "nodeId": node_id or _node_to_str(node.nodeid),
        "children": sorted(children, key=lambda c: c["name"].lower()),
    }


async def read_node_value(node_id: str) -> dict:
    """Read the value of a specific node."""
    client = await get_client()
    node = _parse_node(client, node_id)
    try:
        value = await node.read_value()
        # Handle various OPC-UA types
        if hasattr(value, 'to_string'):
            val_str = value.to_string()
        elif isinstance(value, bytes):
            val_str = value.hex()
        elif value is None:
            val_str = "null"
        else:
            val_str = str(value)
        return {"nodeId": node_id, "value": val_str}
    except Exception as e:
        return {"nodeId": node_id, "value": None, "error": str(e)}


async def write_node_value(node_id: str, value) -> dict:
    """Write a value to a specific node."""
    client = await get_client()
    node = _parse_node(client, node_id)
    try:
        await node.write_value(value)
        return {"nodeId": node_id, "written": True, "value": str(value)}
    except Exception as e:
        return {"nodeId": node_id, "written": False, "error": str(e)}


def _parse_node(client: Client, node_id: str):
    """Parse ns=N;i=X or ns=N;s=NAME into an asyncua Node."""
    # Remove namespace prefix if present
    nid = node_id
    if nid.startswith("ns="):
        parts = nid.split(";")
        ns = int(parts[0].split("=")[1])
        rest = parts[1]
        if rest.startswith("i="):
            ident = int(rest.split("=")[1])
            return client.get_node(f"ns={ns};i={ident}")
        elif rest.startswith("s="):
            name = rest.split("=", 1)[1]
            return client.get_node(f"ns={ns};s={name}")

    # Already a valid asyncua node string
    return client.get_node(nid)


def _node_to_str(nodeid) -> str:
    """Convert NodeId to string representation."""
    ns = nodeid.NamespaceIndex
    ident = nodeid.Identifier
    if isinstance(ident, int):
        return f"ns={ns};i={ident}"
    return f"ns={ns};s={ident}"
