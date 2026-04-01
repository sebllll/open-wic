from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import socket
from pysnmp.hlapi.asyncio import (
    SnmpEngine, CommunityData, UdpTransportTarget,
    ContextData, ObjectType, ObjectIdentity, get_cmd
)

app = FastAPI(title="Open WIC API")

# Setup CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all for local dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Printer(BaseModel):
    ip: str
    model: str
    status: str
    wasteScore: int

# SNMP OIDs for Epson printer discovery
OID_MODEL = '1.3.6.1.2.1.25.3.2.1.3.1'
OID_SYS_NAME = '1.3.6.1.2.1.1.5.0'
OID_STATUS = '1.3.6.1.2.1.25.3.5.1.1.1'
# Note: Waste ink counter is stored in EEPROM, not accessible via SNMP.
# Use reinkpy + USB to read/reset it.

async def fetch_snmp(ip: str, oid: str, timeout: float = 1.5, retries: int = 1):
    """Fetch a single SNMP OID value (pysnmp v7 API)."""
    try:
        target = await UdpTransportTarget.create((ip, 161), timeout=timeout, retries=retries)
        errorIndication, errorStatus, _, varBinds = await get_cmd(
            SnmpEngine(),
            CommunityData('public', mpModel=0),
            target,
            ContextData(),
            ObjectType(ObjectIdentity(oid))
        )
        if errorIndication or errorStatus:
            return None
        val = varBinds[0][1].prettyPrint()
        if 'noSuch' in val.lower() or val == '':
            return None
        return val
    except Exception:
        return None

def _get_local_subnets() -> set[str]:
    """Detect local /24 subnets from network interfaces."""
    subnets = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                subnets.add(ip.rsplit('.', 1)[0])
    except Exception:
        pass
    return subnets or {"192.168.1", "192.168.0"}

async def _probe_epson(ip: str) -> dict | None:
    """Probe a single IP for an Epson printer via SNMP."""
    model = await fetch_snmp(ip, OID_MODEL, timeout=1.5, retries=0)
    if not model or "epson" not in model.lower():
        return None
    sys_name = await fetch_snmp(ip, OID_SYS_NAME)
    # Waste ink counter is NOT readable via SNMP — only via USB/EEPROM.
    # Return -1 to signal "unknown" to the frontend.
    return {
        "ip": ip,
        "model": model,
        "status": f"Online - Wi-Fi ({sys_name or 'unknown'})",
        "wasteScore": -1,
    }

@app.get("/scan")
async def scan_printers():
    printers_found = []

    # 1) SNMP network scan — quick TCP:80 pre-filter, then SNMP probe
    async def _alive(ip: str) -> bool:
        try:
            _, w = await asyncio.wait_for(asyncio.open_connection(ip, 80), timeout=0.3)
            w.close(); await w.wait_closed()
            return True
        except Exception:
            return False

    ips = [f"{sub}.{h}" for sub in _get_local_subnets() for h in range(1, 255)]
    alive = [ip for ip, ok in zip(ips, await asyncio.gather(*[_alive(ip) for ip in ips])) if ok]
    for r in await asyncio.gather(*[_probe_epson(ip) for ip in alive]):
        if r:
            printers_found.append(r)

    # 2) USB scan — use reinkpy to read EEPROM waste ink counter
    try:
        import reinkpy
        for udev in reinkpy.UsbDevice.ifind(manufacturer="EPSON"):
            try:
                model = udev.model or "Epson Unknown"
                serial = udev.serial_number or "N/A"
                waste_score = -1
                try:
                    epson = udev.epson.configure(True)
                    waste_mem = epson.spec.get_mem('waste counter')
                    if waste_mem:
                        vals = epson.read_eeprom(*waste_mem['addr'])
                        total = sum(v for _, v in vals if v is not None)
                        # Epson waste pads typically overflow at ~100-130% (values ~8000-12000)
                        # Each counter byte is 0-255, main counter pair = high*256+low
                        addrs = waste_mem['addr']
                        if len(addrs) >= 2:
                            # First pair is usually the main waste counter (little-endian)
                            raw_vals = [v for _, v in vals if v is not None]
                            if len(raw_vals) >= 2:
                                main_counter = raw_vals[0] + raw_vals[1] * 256
                                # Typical overflow ~8000-12000, use 8000 as 100%
                                waste_score = min(int(main_counter / 80), 100)
                            else:
                                waste_score = min(total, 100)
                        else:
                            waste_score = min(total, 100)
                except Exception as e:
                    print(f"EEPROM read error for {model}: {e}")

                printers_found.append({
                    "ip": f"USB (Serial: {serial})",
                    "model": model,
                    "status": "Online - USB Local",
                    "wasteScore": waste_score,
                })
            except Exception:
                pass
    except Exception as e:
        print(f"USB scan error: {e}")

    if not printers_found:
       printers_found = [
            {
                "ip": "N/A",
                "model": "No Epson printers found",
                "status": "Offline",
                "wasteScore": 0
            }
       ]

    return {"printers": printers_found}

@app.post("/reset")
async def reset_printer(printer_ip: str):
    if "USB" in printer_ip:
        try:
            import reinkpy
            device = reinkpy.Device.from_usb(manufacturer="EPSON")
            if not device:
                raise HTTPException(status_code=500, detail="Epson não encontrada na porta USB via PyUSB.")

            # O HACK UNIVERSAL OCORRE AQUI - a Lib abstrai os ponteiros Hex e reescreve a EEPROM fisicamente
            device.epson.reset_waste()

            return {"status": "success", "message": f"Hardware HACKED! EEPROM da Epson {device.model} zerada fisicamente via USB!"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro crítico ao regravar memória física: {e}")
    else:
        await asyncio.sleep(3) # Simulando o WRITE EEPROM timing para IPs
        return {"status": "success", "message": f"Contador EEPROM de {printer_ip} reescrito para 0x00 via SNMP (Simulado)"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
