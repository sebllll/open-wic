from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
from pysnmp.hlapi.asyncio import (
    SnmpEngine, CommunityData, UdpTransportTarget,
    ContextData, ObjectType, ObjectIdentity, get_cmd
)
import usb.core
import usb.util

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

# Standard SNMP OIDs for printer discovery
OID_MODEL = '1.3.6.1.2.1.25.3.2.1.3.1'        # hrDeviceDescr
OID_SYS_DESCR = '1.3.6.1.2.1.1.1.0'            # sysDescr
OID_SYS_NAME = '1.3.6.1.2.1.1.5.0'             # sysName
OID_STATUS = '1.3.6.1.2.1.25.3.5.1.1.1'        # hrPrinterStatus
# Epson private MIB OIDs (may not be supported on all models)
OID_WASTE_INK_LEVEL = '1.3.6.1.4.1.1248.1.2.2.1.1.1.1.1'
OID_RESET_COMMAND = '1.3.6.1.4.1.1248.1.2.2.1.1.1.1.2'

async def fetch_snmp(ip: str, oid: str, community: str = 'public', timeout: float = 1.5, retries: int = 1):
    """Fetch a single SNMP OID from a target IP using pysnmp v7 API."""
    engine = SnmpEngine()
    try:
        target = await UdpTransportTarget.create((ip, 161), timeout=timeout, retries=retries)
        errorIndication, errorStatus, errorIndex, varBinds = await get_cmd(
            engine,
            CommunityData(community, mpModel=0),
            target,
            ContextData(),
            ObjectType(ObjectIdentity(oid))
        )
        if errorIndication or errorStatus:
            return None
        val = varBinds[0][1].prettyPrint()
        # Filter out "No Such Instance" / "No Such Object" responses
        if 'noSuch' in val.lower() or val == '':
            return None
        return val
    except Exception as e:
        return None

@app.get("/scan")
async def scan_printers():
    printers_found = []

    # 1) Determine local subnets from this machine's network interfaces
    import socket
    local_subnets = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith("127."):
                continue
            parts = ip.rsplit('.', 1)
            local_subnets.add(parts[0])
    except Exception:
        pass
    
    if not local_subnets:
        local_subnets = {"192.168.1", "192.168.0"}
    
    print(f"[scan] Scanning subnets: {local_subnets}")

    # Pre-filter: quick TCP connect to port 80 (most network printers have a web UI)
    async def is_host_alive(ip: str) -> bool:
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, 80), timeout=0.3
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False

    # Build IP list and fast-filter responsive hosts
    ip_list = []
    for subnet in local_subnets:
        for host in range(1, 255):
            ip_list.append(f"{subnet}.{host}")

    print(f"[scan] Checking {len(ip_list)} IPs for active hosts...")
    alive_results = await asyncio.gather(*[is_host_alive(ip) for ip in ip_list])
    alive_ips = [ip for ip, alive in zip(ip_list, alive_results) if alive]
    print(f"[scan] Found {len(alive_ips)} active hosts, probing SNMP...")

    # SNMP probe only alive hosts
    async def probe_ip(ip: str):
        try:
            model = await fetch_snmp(ip, OID_MODEL, timeout=1.5, retries=0)
            if model and ("epson" in model.lower()):
                sys_name = await fetch_snmp(ip, OID_SYS_NAME)
                status_raw = await fetch_snmp(ip, OID_STATUS)
                waste_raw = await fetch_snmp(ip, OID_WASTE_INK_LEVEL)
                waste_score = 0
                if waste_raw:
                    try:
                        waste_score = int(waste_raw)
                    except (ValueError, TypeError):
                        waste_score = 50
                return {
                    "ip": ip,
                    "model": str(model),
                    "status": f"Online - Wi-Fi ({sys_name or status_raw or 'unknown'})",
                    "wasteScore": min(waste_score, 100)
                }
        except Exception:
            pass
        return None

    results = await asyncio.gather(*[probe_ip(ip) for ip in alive_ips])
    for r in results:
        if r:
            printers_found.append(r)

    # 2) USB scan for locally connected Epson printers
    try:
        EPSON_VENDOR_ID = 0x04b8
        devices = usb.core.find(find_all=True, idVendor=EPSON_VENDOR_ID)
        
        for dev in devices:
            try:
                model = usb.util.get_string(dev, dev.iProduct) or "Epson Unknown"
                serial = usb.util.get_string(dev, dev.iSerialNumber) or "N/A"
                
                printers_found.append({
                    "ip": f"USB (Serial: {serial})",
                    "model": model,
                    "status": "Online - USB Local",
                    "wasteScore": 99 
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

@app.get("/scan_ip")
async def scan_single_ip(ip: str):
    """Probe a specific IP address for an Epson printer via SNMP."""
    # Try the standard printer model OID first
    model = await fetch_snmp(ip, OID_MODEL)
    # Fall back to sysDescr if hrDeviceDescr didn't work
    if not model:
        model = await fetch_snmp(ip, OID_SYS_DESCR)
    if not model:
        raise HTTPException(status_code=404, detail=f"No SNMP response from {ip}")
    
    sys_name = await fetch_snmp(ip, OID_SYS_NAME)
    status_raw = await fetch_snmp(ip, OID_STATUS)
    waste_raw = await fetch_snmp(ip, OID_WASTE_INK_LEVEL)
    waste_score = 0
    if waste_raw:
        try:
            waste_score = int(waste_raw)
        except (ValueError, TypeError):
            waste_score = 50

    return {"printers": [{
        "ip": ip,
        "model": str(model),
        "status": f"Online - Wi-Fi ({sys_name or status_raw or 'unknown'})",
        "wasteScore": min(waste_score, 100)
    }]}

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
