"""MQTT Explorer — connect to MQTT brokers, browse topics, collect messages.

Uses paho-mqtt for connection management. Supports:
- Connect/disconnect to arbitrary MQTT brokers
- Subscribe to wildcard topics
- Collect recent messages per topic
- Publish messages
"""

import asyncio
import json
import threading
import time
from dataclasses import dataclass, field
from collections import defaultdict

import paho.mqtt.client as mqtt

# ── State ─────────────────────────────────────────────────────────

@dataclass
class BrokerState:
    host: str
    port: int = 8883
    connected: bool = False
    topics: dict[str, dict] = field(default_factory=dict)  # topic -> {count, last_message, last_time}
    messages: list[dict] = field(default_factory=list)     # recent messages
    start_time: float = 0

_state: BrokerState | None = None
_client: mqtt.Client | None = None
_max_messages = 200
_loop_thread = None


# ── Public API ────────────────────────────────────────────────────

def connect(host: str, port: int = 8883) -> dict:
    """Connect to an MQTT broker. Returns status dict."""
    global _state, _client, _loop_thread

    # Disconnect existing
    if _client:
        try:
            _client.disconnect()
        except Exception:
            pass

    _state = BrokerState(host=host, port=port)
    _client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    _client.on_connect = _on_connect
    _client.on_message = _on_message
    _client.on_disconnect = _on_disconnect

    try:
        _client.connect(host, port, 60)
        _loop_thread = threading.Thread(target=_client.loop_forever, daemon=True)
        _loop_thread.start()

        # Wait for connection
        for _ in range(30):  # 3 seconds max
            if _state.connected:
                _state.start_time = time.time()
                # Subscribe to all topics
                _client.subscribe("#")
                return {"connected": True, "host": host, "port": port}
            time.sleep(0.1)

        return {"connected": False, "error": "Connection timeout"}
    except Exception as e:
        return {"connected": False, "error": str(e)}


def disconnect() -> dict:
    """Disconnect from the current broker."""
    global _state, _client
    if _client:
        try:
            _client.disconnect()
        except Exception:
            pass
    _client = None
    _state = None
    return {"connected": False}


def get_state() -> dict:
    """Get current connection state and topic overview."""
    if not _state:
        return {"connected": False}
    return {
        "connected": _state.connected,
        "host": _state.host,
        "port": _state.port,
        "uptime": round(time.time() - _state.start_time, 1) if _state.connected else 0,
        "topic_count": len(_state.topics),
        "message_count": len(_state.messages),
    }


def get_topics() -> list[dict]:
    """Get topic tree."""
    if not _state:
        return []
    topics = []
    for path, info in sorted(_state.topics.items()):
        topics.append({
            "path": path,
            "count": info["count"],
            "lastMessage": info.get("last_message", ""),
            "lastTime": info.get("last_time", 0),
        })
    return topics


def get_messages(topic: str = None, limit: int = 50) -> list[dict]:
    """Get recent messages, optionally filtered by topic."""
    if not _state:
        return []
    msgs = _state.messages
    if topic:
        msgs = [m for m in msgs if m["topic"] == topic]
    return msgs[-limit:]


def publish(topic: str, payload: str, qos: int = 0, retain: bool = False) -> dict:
    """Publish a message to the current broker."""
    if not _client or not _state or not _state.connected:
        return {"error": "Not connected"}
    try:
        msg_info = _client.publish(topic, payload, qos=qos, retain=retain)
        return {"published": True, "topic": topic, "mid": msg_info.mid}
    except Exception as e:
        return {"error": str(e)}


# ── Callbacks ─────────────────────────────────────────────────────

def _on_connect(client, userdata, flags, rc, props=None):
    if _state:
        _state.connected = (rc == 0)


def _on_disconnect(client, userdata, rc, props=None):
    if _state:
        _state.connected = False


def _on_message(client, userdata, msg):
    if not _state:
        return
    try:
        payload_str = msg.payload.decode("utf-8", errors="replace")
    except Exception:
        payload_str = str(msg.payload)[:200]

    now = time.time()

    # Update topic stats
    _state.topics[msg.topic] = {
        "count": _state.topics.get(msg.topic, {}).get("count", 0) + 1,
        "last_message": payload_str[:200],
        "last_time": now,
    }

    # Store message
    _state.messages.append({
        "topic": msg.topic,
        "payload": payload_str[:500],
        "qos": msg.qos,
        "retain": msg.retain,
        "time": now,
    })

    # Trim
    if len(_state.messages) > _max_messages:
        _state.messages = _state.messages[-_max_messages:]
