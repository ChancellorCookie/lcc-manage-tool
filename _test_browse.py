from asyncua import Client
import asyncio

async def test():
    c = Client(url='opc.tcp://10.89.11.52:4840', timeout=30)
    await c.connect()
    
    objs = c.get_objects_node()
    print("=== Objects node children ===")
    for ch in await objs.get_children():
        br = await ch.read_browse_name()
        print(f"  {br.Name} (ns={br.NamespaceIndex}, i={ch.nodeid.Identifier})")
    
    ds = await objs.get_child("3:DeviceSet")
    if ds:
        print("\n=== DeviceSet children ===")
        kids = await ds.get_children()
        print(f"  Count: {len(kids)}")
        for ch in kids[:5]:
            br = await ch.read_browse_name()
            print(f"  {br.Name} (ns={br.NamespaceIndex}, i={ch.nodeid.Identifier})")
        if len(kids) > 5:
            print(f"  ... and {len(kids)-5} more")
    
    await c.disconnect()

asyncio.run(test())
