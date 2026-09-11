"""OPC-UA-Client für LADS-Discovery (kein REST nötig).

Struktur (geprobt am LADSProxy):
  Objects → DeviceSet → Geräte (String-nodeId ns=X;s=SERIAL)
    → FunctionalUnitSet → Units → FunctionSet → Funktionen
      → SensorValue (Wert) + EngineeringUnits-Property + Historizing-Attribut
"""
from asyncua import Client, ua

DEVICE_SET = "DeviceSet"
FUNCTIONAL_UNIT_SET = "FunctionalUnitSet"
FUNCTION_SET = "FunctionSet"
SENSOR_VALUE = "SensorValue"
ENGINEERING_UNITS = "EngineeringUnits"


def node_to_str(nodeid) -> str:
    ns = nodeid.NamespaceIndex
    ident = nodeid.Identifier
    if isinstance(ident, int):
        return f"ns={ns};i={ident}"
    return f"ns={ns};s={ident}"


def _is_string_node(node) -> bool:
    return isinstance(node.nodeid.Identifier, str)


def _plain(value) -> str:
    if value is None:
        return ""
    s = str(value)
    return "" if s.startswith("LocalizedText") else s


async def _find_child(node, name):
    try:
        for ch in await node.get_children():
            bn = await ch.read_browse_name()
            if bn.Name == name:
                return ch
    except Exception:
        pass
    return None


async def _safe_read(node):
    """DataValue lesen, auch bei Bad-Status. Liefert (value, timestamp)."""
    try:
        dv = await node.read_attribute(ua.AttributeIds.Value, None, False)
        sc = dv.StatusCode
        val = dv.Value.Value if sc.is_good() else None
        ts = dv.SourceTimestamp or dv.ServerTimestamp
        return val, ts
    except Exception:
        return None, None


async def _read_meta(client, node_id_str):
    """ComponentName + HierarchicalLocation eines Geräts."""
    out = {"component_name": "", "hierarchical_location": ""}

    async def read(rel):
        node = client.get_node(f"{node_id_str}-{rel}")
        v, _ = await _safe_read(node)
        return _plain(v)

    try:
        v = await read("ComponentName")
        if v:
            out["component_name"] = v
    except Exception:
        pass
    if not out["component_name"]:
        try:
            out["component_name"] = await read("Identification-ComponentName")
        except Exception:
            pass
    try:
        loc = await read("HierarchicalLocation")
        if loc:
            out["hierarchical_location"] = loc.removeprefix("IEU/").removeprefix("ieu/")
    except Exception:
        pass
    return out


async def _read_identification(device_node):
    out = {"device_class": "", "manufacturer": "", "model": ""}
    ident = await _find_child(device_node, "Identification")
    if ident is None:
        return out
    for key, name in (("device_class", "DeviceClass"), ("manufacturer", "Manufacturer"), ("model", "Model")):
        ch = await _find_child(ident, name)
        if ch is not None:
            v, _ = await _safe_read(ch)
            if v is not None:
                out[key] = _plain(v)
    return out


async def _browse_signals(device_node):
    signals = []
    fus = await _find_child(device_node, FUNCTIONAL_UNIT_SET)
    if fus is None:
        return signals
    for unit in await fus.get_children():
        if not _is_string_node(unit):
            continue
        unit_bn = await unit.read_browse_name()
        unit_name = unit_bn.Name
        fset = await _find_child(unit, FUNCTION_SET)
        if fset is None:
            continue
        seen = set()
        for fn in await fset.get_children():
            if not _is_string_node(fn):
                continue
            fn_bn = await fn.read_browse_name()
            fname = fn_bn.Name
            if fname in seen:
                continue
            seen.add(fname)
            sv = await _find_child(fn, SENSOR_VALUE)
            if sv is None:
                continue  # Kontroll-Funktion (z.B. Switch) ohne SensorValue
            value, ts = await _safe_read(sv)
            unit_str = ""
            eu = await _find_child(sv, ENGINEERING_UNITS)
            if eu is not None:
                euv, _ = await _safe_read(eu)
                dn = getattr(euv, "DisplayName", None)
                if dn is not None:
                    unit_str = getattr(dn, "Text", None) or str(dn)
            historizing = False
            try:
                dv = await sv.read_attribute(ua.AttributeIds.Historizing)
                historizing = bool(dv.Value.Value)
            except Exception:
                pass
            signals.append({
                "browse_name": fname,
                "display_name": fname,
                "unit_browse_name": unit_name,
                "engineering_unit": unit_str,
                "historizing": historizing,
                "node_id": node_to_str(sv.nodeid),
                "last_value": "" if value is None else str(value),
                "last_ts": ts.isoformat() if ts else "",
            })
    return signals


async def list_devices(url: str) -> list:
    """Geräte eines OPC-UA-Servers auflisten (ohne Signale).

    Dasselbe Gerät (gleiche Serial) erscheint in mehreren Namespaces — mal
    mit ComponentName/Location, mal als Stub ohne Metadaten. Wir mergen über
    alle Vorkommen und ziehen nicht-leere Werte vor.
    """
    client = Client(url=url, timeout=30)
    await client.connect()
    try:
        objects = client.get_objects_node()
        deviceset = await _find_child(objects, DEVICE_SET)
        if deviceset is None:
            raise RuntimeError("Kein 'DeviceSet'-Knoten unter Objects gefunden")
        merged: dict = {}
        for ch in await deviceset.get_children():
            if not _is_string_node(ch):
                continue
            serial = ch.nodeid.Identifier
            bn = await ch.read_browse_name()
            meta = await _read_meta(client, node_to_str(ch.nodeid))
            ident = await _read_identification(ch)
            entry = merged.setdefault(serial, {
                "serial": serial,
                "browse_name": bn.Name,
                "component_name": "",
                "hierarchical_location": "",
                "device_class": "",
                "manufacturer": "",
                "model": "",
            })
            entry["component_name"] = entry["component_name"] or meta["component_name"]
            entry["hierarchical_location"] = entry["hierarchical_location"] or meta["hierarchical_location"]
            entry["device_class"] = entry["device_class"] or ident["device_class"]
            entry["manufacturer"] = entry["manufacturer"] or ident["manufacturer"]
            entry["model"] = entry["model"] or ident["model"]
        devices = list(merged.values())
        for d in devices:
            if not d["component_name"]:
                d["component_name"] = d["serial"]  # Geräte ohne ComponentName → Serial
        return devices
    finally:
        await client.disconnect()


async def list_signals(url: str, serial: str) -> list:
    """Signale EINES Geräts live browsen (für Lazy-Expand im UI)."""
    client = Client(url=url, timeout=30)
    await client.connect()
    try:
        objects = client.get_objects_node()
        deviceset = await _find_child(objects, DEVICE_SET)
        if deviceset is None:
            return []
        node = None
        for ch in await deviceset.get_children():
            if _is_string_node(ch) and ch.nodeid.Identifier == serial:
                node = ch
                break
        if node is None:
            return []
        return await _browse_signals(node)
    finally:
        await client.disconnect()


async def list_all_signals(url: str) -> dict:
    """Alle Geräte + Signale in EINER Verbindung browsen (für Discovery/Reparatur).

    → {serial: [signal-dicts]} — robuster als pro Gerät eine eigene Verbindung,
    wenn der LADS-Server viele Geräte hat (vermeidet Verbindungs-Churn).
    """
    client = Client(url=url, timeout=60)
    await client.connect()
    try:
        objects = client.get_objects_node()
        deviceset = await _find_child(objects, DEVICE_SET)
        if deviceset is None:
            return {}
        out: dict = {}
        for ch in await deviceset.get_children():
            if not _is_string_node(ch):
                continue
            serial = ch.nodeid.Identifier
            try:
                out[serial] = await _browse_signals(ch)
            except Exception:
                out[serial] = []
        return out
    finally:
        await client.disconnect()
