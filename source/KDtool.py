import os
import sys
import traceback
import time as _time
import atexit as _atexit

#########################################
# STARTVORBEREITUNGEN
# Beim Start wird das Arbeitsverzeichnis aus dem Temp-Ordner
# herausgelegt, damit PyInstaller später alles löschen kann.
#########################################
_exe_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
os.chdir(_exe_dir)

#########################################
# ALTE TEMP-DATEIEN AUFRÄUMEN
# Nach einem Update bleiben manchmal alte _MEI*-Ordner
# und .update_bak-Dateien übrig – die werden hier gelöscht.
#########################################
if getattr(sys, 'frozen', False):
    try:
        _own_mei = sys._MEIPASS.lower().rstrip("\\")
        for _d in os.listdir(os.environ.get("TEMP", "C:\\Windows\\Temp")):
            _dp = os.path.join(os.environ.get("TEMP", "C:\\Windows\\Temp"), _d)
            if _d.startswith("_MEI") and os.path.isdir(_dp) and _dp.lower().rstrip("\\") != _own_mei:
                try:
                    import shutil
                    shutil.rmtree(_dp, ignore_errors=True)
                except:
                    pass
    except:
        pass

for _dir in (_exe_dir, os.environ.get("TEMP", "C:\\Windows\\Temp")):
    try:
        for _f in os.listdir(_dir):
            if _f.endswith(".update_bak"):
                _p = os.path.join(_dir, _f)
                try:
                    os.remove(_p)
                except:
                    pass
    except:
        pass

#########################################
# FEHLERPROTOKOLLIERUNG
# Wenn das Programm abstürzt, wird der Fehler in die
# Datei kd_error.log geschrieben und als Pop-up angezeigt.
#########################################
_log_file = os.path.join(_exe_dir, "kd_error.log")

def _global_excepthook(exc_type, exc_value, exc_tb):
    with open(_log_file, "a") as f:
        f.write(f"=== {_time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
        f.write("\n")
    try:
        import tkinter.messagebox as _mb
        _mb.showerror("Fehler", f"{exc_type.__name__}: {exc_value}")
    except:
        pass

sys.excepthook = _global_excepthook

#########################################
# TCL/TK PFADE FÜR PYINSTALLER
# Wird nur im gebauten EXE gebraucht (Python 3.14 Workaround).
#########################################
if getattr(sys, 'frozen', False):
    _tcl_dir = os.path.join(sys._MEIPASS, '_tcl_data')
    _tk_dir = os.path.join(sys._MEIPASS, '_tk_data')
    if os.path.isdir(_tcl_dir):
        os.environ['TCL_LIBRARY'] = _tcl_dir
    if os.path.isdir(_tk_dir):
        os.environ['TK_LIBRARY'] = _tk_dir

#########################################
# BENÖTIGTE PROGRAMMBIBLIOTHEKEN
#########################################
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import socket
import subprocess
import platform
import os
import time
import threading
import ctypes
import ctypes.wintypes
import sys
import re
import json
import tempfile
import shutil
import webbrowser
import urllib.request
from datetime import datetime

CREATE_NO_WINDOW = 0x08000000

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except:
        pass


#########################################
# FENSTER-DESIGN
# Setzt die blaue Titelzeile und weisse Schrift.
#########################################
def set_titlebar_style(window):
    try:
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        DWMWA_CAPTION_COLOR = 35
        DWMWA_TEXT_COLOR = 36
        blue = 0x00D77800
        white = 0x00FFFFFF
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.wintypes.HWND(hwnd), ctypes.wintypes.DWORD(DWMWA_CAPTION_COLOR),
            ctypes.byref(ctypes.wintypes.DWORD(blue)), ctypes.sizeof(ctypes.wintypes.DWORD))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.wintypes.HWND(hwnd), ctypes.wintypes.DWORD(DWMWA_TEXT_COLOR),
            ctypes.byref(ctypes.wintypes.DWORD(white)), ctypes.sizeof(ctypes.wintypes.DWORD))
    except:
        pass


def _subprocess_kwargs():
    if sys.platform == "win32":
        return {"creationflags": CREATE_NO_WINDOW}
    return {}


def _oem_encoding():
    try:
        cp = ctypes.windll.kernel32.GetOEMCP()
        return f"cp{cp}"
    except:
        return "cp850"


#########################################
# POWERSHELL AUSFÜHREN
# Führt einen PowerShell-Befehl aus und gibt
# das Ergebnis als Text zurück.
#########################################
def run_powershell(command, bypass_policy=False):
    args = ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden"]
    if bypass_policy:
        args.extend(["-ExecutionPolicy", "Bypass"])
    args.extend(["-Command", command])
    return subprocess.check_output(
        args,
        text=True,
        encoding="utf-8",
        errors="ignore",
        **_subprocess_kwargs(),
    )


#########################################
# ADMIN-RECHTE PRÜFEN
# Prüft, ob das Programm mit Administrator-Rechten läuft.
# Falls nicht, kann es neu gestartet werden (mit Zustimmung des Benutzers).
#########################################
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False

def restart_as_admin(extra_flag=""):
    if is_admin():
        return True
    try:
        script = os.path.abspath(sys.argv[0])
        params = ' '.join([f'"{arg}"' for arg in sys.argv[1:]])
        extra = f" {extra_flag}" if extra_flag else ""
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script}" {params}{extra}', None, 1)
        sys.exit(0)
    except:
        return False

stop_event = threading.Event()
app_running = True
vlan_scan_id = 0

#########################################
# NETZWERK-FUNKTIONEN
# Ab hier kommen alle Funktionen rund um die Netzwerk-Abfragen.
#########################################
def no_connection_network():
    return {
        "ip": "Keine Verbindung",
        "subnet": "-",
        "prefix": 24,
        "gateway": "-",
        "iface": "-",
        "dns1": "",
        "dns2": "",
        "extended_ips": "",
        "extended_list": [],
    }


def format_ip_display(ip, extended_ips=""):
    if not extended_ips or ip in ("Keine Verbindung", "Fehler"):
        return ip
    return f"{ip}  (Erweiterte Netzwerke: {extended_ips})"


def benutzer_fehlermeldung(exc=None):
    if exc is None:
        return "Ein unbekannter Fehler ist aufgetreten."
    if isinstance(exc, FileNotFoundError):
        return "Die angegebene Datei wurde nicht gefunden."
    if isinstance(exc, PermissionError):
        return "Keine Berechtigung für diese Aktion."
    if isinstance(exc, subprocess.CalledProcessError):
        return "Ein externer Befehl wurde mit Fehler beendet."
    text = str(exc).lower()
    if "winget" in text:
        return "Die Installation ueber winget ist fehlgeschlagen."
    if "urlopen" in text or "network" in text or "10061" in text or "10060" in text:
        return "Netzwerkfehler beim Download."
    return "Ein unbekannter Fehler ist aufgetreten."


def ipv4_to_int(ip):
    parts = ip.split(".")
    return (int(parts[0]) << 24) + (int(parts[1]) << 16) + (int(parts[2]) << 8) + int(parts[3])


def same_subnet_as_gateway(ip, gateway, prefix):
    mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
    return (ipv4_to_int(ip) & mask) == (ipv4_to_int(gateway) & mask)


def split_primary_and_extended_ips(addresses, gateway):
    if not addresses:
        return "", 24, []

    gateway_subnet = [
        (ip, prefix) for ip, prefix in addresses if same_subnet_as_gateway(ip, gateway, prefix)
    ]
    if gateway_subnet:
        primary_ip, primary_prefix = gateway_subnet[0]
        extended = sorted({(ip, p) for ip, p in addresses if ip != primary_ip}, key=lambda x: x[0])
        return primary_ip, primary_prefix, extended

    primary_ip, primary_prefix = addresses[0]
    extended = sorted({(ip, p) for ip, p in addresses[1:]}, key=lambda x: x[0])
    return primary_ip, primary_prefix, extended


def prefix_to_mask(prefix):
    mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
    return ".".join(str((mask >> shift) & 255) for shift in (24, 16, 8, 0))


def get_network():
    ps = r"""
    $upIndexes = @(Get-NetAdapter | Where-Object { $_.Status -eq 'Up' } | Select-Object -ExpandProperty ifIndex)
    if ($upIndexes.Count -eq 0) { Write-Output "KEINE_VERBINDUNG"; exit }

    $route = Get-NetRoute -DestinationPrefix "0.0.0.0/0" |
        Where-Object { $upIndexes -contains $_.InterfaceIndex } |
        Sort-Object RouteMetric | Select-Object -First 1
    if (-not $route) { Write-Output "KEINE_VERBINDUNG"; exit }

    $iface = Get-NetIPConfiguration -InterfaceIndex $route.InterfaceIndex -ErrorAction SilentlyContinue
    if (-not $iface) { Write-Output "KEINE_VERBINDUNG"; exit }

    $addresses = @(Get-NetIPAddress -InterfaceIndex $iface.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress } |
        ForEach-Object { "$($_.IPAddress)/$($_.PrefixLength)" })
    if ($addresses.Count -eq 0) { Write-Output "KEINE_VERBINDUNG"; exit }

    $gateway = $route.NextHop
    $dns = (Get-DnsClientServerAddress -InterfaceIndex $iface.InterfaceIndex -AddressFamily IPv4).ServerAddresses
    $dns1 = if ($dns.Count -ge 1) { $dns[0] } else { "" }
    $dns2 = if ($dns.Count -ge 2) { $dns[1] } else { "" }
    $addrStr = $addresses -join "|"
    "$addrStr;$gateway;$($iface.InterfaceAlias);$dns1;$dns2"
    """
    try:
        out = run_powershell(ps).strip()
        if out == "KEINE_VERBINDUNG":
            return no_connection_network()

        parts = out.split(";")
        addr_entries = [entry for entry in parts[0].split("|") if "/" in entry]
        gateway = parts[1]
        iface = parts[2]
        dns1 = parts[3] if len(parts) > 3 else ""
        dns2 = parts[4] if len(parts) > 4 else ""

        addresses = []
        for entry in addr_entries:
            ip, prefix = entry.split("/", 1)
            addresses.append((ip.strip(), int(prefix)))

        primary_ip, primary_prefix, extended = split_primary_and_extended_ips(addresses, gateway)
        if not primary_ip:
            return no_connection_network()

        extended_ips = ", ".join(ip for ip, _ in extended)
        return {
            "ip": primary_ip,
            "subnet": prefix_to_mask(primary_prefix),
            "prefix": primary_prefix,
            "gateway": gateway,
            "iface": iface,
            "dns1": dns1,
            "dns2": dns2,
            "extended_ips": extended_ips,
            "extended_list": extended,
        }
    except Exception:
        return no_connection_network()


def get_dhcp_status():
    ps = r"""
    $route = Get-NetRoute -DestinationPrefix "0.0.0.0/0" | Sort-Object RouteMetric | Select-Object -First 1
    if (-not $route) { "Keine Verbindung"; exit }
    $adapter = Get-NetAdapter -InterfaceIndex $route.InterfaceIndex
    $guid = $adapter.InterfaceGuid
    $regPath = "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\$guid"
    $dhcp = (Get-ItemProperty -Path $regPath -Name EnableDHCP -ErrorAction SilentlyContinue).EnableDHCP
    if ($dhcp -eq 1) { "Ja" } else { "Nein" }
    """
    try:
        return run_powershell(ps).strip()
    except Exception:
        return "Keine Verbindung"

def validate_static_fields(ip, subnet, gateway, dns1):
    missing = []
    if not str(ip).strip():
        missing.append("IP-Adresse")
    if not str(subnet).strip():
        missing.append("Subnetz")
    if not str(gateway).strip():
        missing.append("Gateway")
    if not str(dns1).strip():
        missing.append("DNS1")
    if missing:
        return False, f"❌ Pflichtfelder fehlen: {', '.join(missing)}"
    return True, ""


def subnet_to_prefix(subnet):
    if "." in str(subnet):
        parts = str(subnet).strip().split(".")
        if len(parts) != 4:
            raise ValueError("invalid mask")
        return sum(bin(int(x)).count("1") for x in parts)
    return int(subnet)


def set_dhcp():
    ps = r"""
    $route = Get-NetRoute -DestinationPrefix "0.0.0.0/0" | Sort-Object RouteMetric | Select-Object -First 1
    $index = $route.ifIndex

    Get-NetIPAddress -InterfaceIndex $index -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue

    Get-NetRoute -InterfaceIndex $index -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.DestinationPrefix -eq '0.0.0.0/0' } |
        Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue

    Set-NetIPInterface -InterfaceIndex $index -AddressFamily IPv4 -Dhcp Enabled -ErrorAction Stop
    Set-DnsClientServerAddress -InterfaceIndex $index -ResetServerAddresses -ErrorAction SilentlyContinue
    ipconfig /renew | Out-Null
    "DHCP wurde vollständig aktiviert."
    """
    try:
        run_powershell(ps, bypass_policy=True)
        return "✅ Vollständig auf DHCP umgeschaltet (IP + DNS)"
    except Exception:
        return "❌ Fehler beim Umschalten auf DHCP"


def set_static_ip(ip, subnet, gateway, dns1, dns2, extended_ips=None):
    ip = str(ip).strip()
    subnet = str(subnet).strip()
    gateway = str(gateway).strip()
    dns1 = str(dns1).strip()
    dns2 = str(dns2).strip()

    ok, message = validate_static_fields(ip, subnet, gateway, dns1)
    if not ok:
        return message

    try:
        prefix = subnet_to_prefix(subnet)
        if prefix < 1 or prefix > 32:
            raise ValueError("invalid prefix")
    except Exception:
        return "❌ Ungültiges Subnetz! Bitte 255.255.255.0 oder 24 eingeben."

    dns_servers = [dns1]
    if dns2:
        dns_servers.append(dns2)
    dns_ps = ", ".join(f'"{d}"' for d in dns_servers)

    ext_ps = ""
    ext_summary = []
    if extended_ips:
        for ext_ip, ext_sub in extended_ips:
            ext_ip = ext_ip.strip()
            ext_sub = ext_sub.strip()
            if not ext_ip:
                continue
            if not ext_sub:
                ext_sub = subnet
            try:
                ext_prefix = subnet_to_prefix(ext_sub)
            except Exception:
                continue
            ext_ps += f"""
        New-NetIPAddress -InterfaceIndex $index -AddressFamily IPv4 `
            -IPAddress "{ext_ip}" -PrefixLength {ext_prefix} -ErrorAction Stop | Out-Null
"""
            ext_summary.append(f"{ext_ip}/{ext_prefix}")

    ps = rf"""
    try {{
        $route = Get-NetRoute -DestinationPrefix "0.0.0.0/0" | Sort-Object RouteMetric | Select-Object -First 1
        $index = $route.ifIndex

        Get-NetIPAddress -InterfaceIndex $index -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue

        Get-NetRoute -InterfaceIndex $index -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object {{ $_.DestinationPrefix -eq '0.0.0.0/0' }} |
            Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue

        Set-DnsClientServerAddress -InterfaceIndex $index -ResetServerAddresses -ErrorAction SilentlyContinue

        Set-NetIPInterface -InterfaceIndex $index -AddressFamily IPv4 -Dhcp Disabled -ErrorAction Stop

        New-NetIPAddress -InterfaceIndex $index -AddressFamily IPv4 `
            -IPAddress "{ip}" -PrefixLength {prefix} -DefaultGateway "{gateway}" -ErrorAction Stop | Out-Null
{ext_ps}
        Set-DnsClientServerAddress -InterfaceIndex $index -ServerAddresses @({dns_ps}) -ErrorAction Stop

        "ERFOLG"
    }}
    catch {{
        "FEHLER: $($_.Exception.Message)"
    }}
    """
    try:
        result = run_powershell(ps, bypass_policy=True).strip()

        if "ERFOLG" in result:
            dns_text = ", ".join(dns_servers)
            msg = f"✅ Fixe IP erfolgreich gesetzt!\nIP: {ip}\nSubnetz: {subnet}\nGateway: {gateway}\nDNS: {dns_text}"
            if ext_summary:
                msg += "\nErweiterte IPs: " + ", ".join(ext_summary)
            return msg
        if "FEHLER:" in result:
            return "❌ Fehler beim Setzen der festen IP-Adresse."
        return "❌ Fehler beim Setzen der festen IP-Adresse."
    except Exception:
        return "❌ Fehler beim Setzen der festen IP-Adresse."

#########################################
# WINDOWS-INFORMATIONEN
# Liest grundlegende Windows-Informationen aus.
#########################################
def windows_info():
    return {
        "PC Name": platform.node(),
        "Version": platform.version(),
        "Release": platform.release(),
    }


#########################################
# LETZTES WINDOWS-UPDATE
# Fragt das Datum des letzten Windows-Updates ab.
#########################################
def get_last_windows_update():
    ps = r"""
    $update = Get-HotFix | Where-Object { $_.InstalledOn } | Sort-Object InstalledOn -Descending | Select-Object -First 1
    if ($update) { Get-Date $update.InstalledOn -Format 'dd.MM.yyyy' }
    """
    try:
        out = run_powershell(ps).strip()
        return out if out else "Nicht verfügbar"
    except Exception:
        return "Nicht verfügbar"

#########################################
# INTERNETVERBINDUNG PRÜFEN
# Versucht, über bekannte DNS-Server (Google, Cloudflare)
# eine Verbindung ins Internet herzustellen.
#########################################
def internet_status():
    for dns in ("8.8.8.8", "1.1.1.1", "208.67.222.222", "8.8.4.4"):
        try:
            socket.create_connection((dns, 53), timeout=2)
            return "✅ Internetverbindung OK"
        except:
            continue
    return "❌ Kein Internet"


def is_ipv4_address(value):
    parts = value.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(part) <= 255 for part in parts)
    except ValueError:
        return False


def get_device_name(ip_addr, mac):
    try:
        socket.setdefaulttimeout(0.8)
        return socket.gethostbyaddr(ip_addr)[0]
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["nbtstat", "-A", ip_addr],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=2,
            **_subprocess_kwargs(),
        )
        for line in result.stdout.splitlines():
            if "<00>" in line and "UNIQUE" in line.upper():
                parts = line.split()
                if parts and parts[0] not in ("Name", "MAC"):
                    return parts[0]
    except Exception:
        pass

    return "-"


#########################################
# FIREWALL-STATUS ABFRAGEN
# Liest den Status der Firewall (Privat/Öffentlich).
#########################################
def get_firewall_status():
    try:
        ps = 'Get-NetFirewallProfile | ForEach-Object { "$($_.Name):$($_.Enabled)" }'
        out = run_powershell(ps).strip()
        result = {}
        for line in out.splitlines():
            if ":" not in line:
                continue
            name, enabled = line.split(":", 1)
            result[name.strip().lower()] = enabled.strip().lower() == "true"
        return result
    except Exception:
        return None


#########################################
# DRUCKER ABFRAGEN
# Ruft alle installierten Drucker inklusive
# IP, Aufträgen und Fehlerstatus ab.
#########################################
def get_printers():
    try:
        ps = r"""
        $printers = Get-Printer; $ports = Get-PrinterPort
        foreach ($p in $printers) {
            $port = $ports | Where-Object { $_.Name -eq $p.PortName }
            $ip = if ($port -and $port.PrinterHostAddress) { $port.PrinterHostAddress } elseif ($p.PortName -match "\d+\.\d+\.\d+\.\d+") { $p.PortName } else { $p.PortName }
            $jobs = Get-PrintJob -PrinterName $p.Name -ErrorAction SilentlyContinue
            $jobCount = ($jobs | Measure-Object).Count
            $hasError = if ($jobs | Where-Object { $_.JobStatus -match 'Error' }) { 1 } else { 0 }
            "$($p.Name)|$ip|$jobCount|$hasError"
        }
        """
        out = run_powershell(ps)
        result = []
        for line in out.splitlines():
            if "|" in line:
                parts = line.split("|", 3)
                name = parts[0]
                ip = parts[1]
                job_count = parts[2] if len(parts) > 2 else "0"
                error_flag = parts[3] if len(parts) > 3 else "0"
                result.append((name, ip, job_count, error_flag))
        if not result:
            result = [("Keine Drucker gefunden", "Spooler prüfen", "0", "0")]
        return result
    except:
        return [("Keine Drucker gefunden", "Spooler prüfen", "0", "0")]

def load_vlan(primary_tree, extended_tree, root, ip, extended_list, progress_label=None, progress_bar=None, on_scan_done=None):
    global vlan_scan_id
    if not ip or ip == "Fehler" or "." not in ip:
        if on_scan_done:
            try: root.after(0, on_scan_done)
            except: pass
        return

    vlan_scan_id += 1
    scan_id = vlan_scan_id

    bases = set()
    primary_base = ".".join(ip.split(".")[:3])
    bases.add(primary_base)
    for ext_ip, _ in extended_list:
        bases.add(".".join(ext_ip.split(".")[:3]))

    all_targets = []
    target_base_map = {}
    for base in bases:
        for i in range(1, 255):
            t = f"{base}.{i}"
            all_targets.append(t)
            target_base_map[t] = base

    total_targets = len(all_targets)

    if progress_bar is not None:
        try:
            root.after(0, lambda: progress_bar.config(maximum=total_targets, value=0))
        except:
            pass

    if progress_label is not None:
        try:
            root.after(0, lambda: progress_label.config(
                text=f"Scanne {total_targets} Adressen …"
            ))
        except:
            pass

    def worker():
        from concurrent.futures import ThreadPoolExecutor, as_completed

        completed = 0

        def ping_one(ip):
            subprocess.run(
                ["ping", "-n", "1", "-w", "100", ip],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                **_subprocess_kwargs(),
            )
            return ip

        with ThreadPoolExecutor(max_workers=50) as pool:
            futures = {pool.submit(ping_one, t): t for t in all_targets}
            for future in as_completed(futures):
                if scan_id != vlan_scan_id or not app_running or stop_event.is_set():
                    pool.shutdown(wait=False, cancel_futures=True)
                    return
                completed += 1
                if progress_bar is not None and completed % 5 == 0:
                    try:
                        root.after(0, lambda v=completed: progress_bar.config(value=v))
                    except:
                        pass

        if scan_id != vlan_scan_id or not app_running or stop_event.is_set():
            return

        if progress_label is not None:
            try:
                root.after(0, lambda: progress_label.config(text="Lese ARP-Tabelle aus …"))
            except:
                pass

        arp_out = subprocess.run(
            ["arp", "-a"], capture_output=True, text=True, encoding="utf-8", errors="ignore",
            **_subprocess_kwargs(),
        ).stdout

        if progress_label is not None:
            try:
                root.after(0, lambda: progress_label.config(text="Verarbeite ARP-Einträge …"))
            except:
                pass

        entries = {}
        own_ip = ip
        for line in arp_out.splitlines():
            if "-" not in line:
                continue
            parts = line.split()
            if len(parts) < 2 or scan_id != vlan_scan_id or not app_running:
                continue
            ip_addr, mac = parts[0], parts[1]
            if not is_ipv4_address(ip_addr):
                continue
            addr_base = ".".join(ip_addr.split(".")[:3])
            if addr_base not in bases:
                continue
            is_primary = (addr_base == primary_base)
            name = get_device_name(ip_addr, mac)
            entries[ip_addr] = (name, mac, is_primary)

        if progress_label is not None:
            try:
                root.after(0, lambda: progress_label.config(text="Sortiere Einträge …"))
            except:
                pass

        if scan_id == vlan_scan_id and app_running and not stop_event.is_set():
            if own_ip not in entries:
                own_mac = "-"
                try:
                    ps = f'Get-NetIPAddress -IPAddress "{own_ip}" | Get-NetAdapter | Select-Object -ExpandProperty MacAddress'
                    out = subprocess.run(
                        ["powershell", "-NoProfile", "-Command", ps],
                        capture_output=True, text=True, encoding="utf-8", errors="ignore",
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    ).stdout.strip()
                    if out:
                        own_mac = out
                except:
                    pass
                entries[own_ip] = (socket.gethostname(), own_mac, True)
            for ext_ip, _ in extended_list:
                if ext_ip not in entries:
                    entries[ext_ip] = (socket.gethostname(), "-", False)

        def insert_entries():
            if not root.winfo_exists() or scan_id != vlan_scan_id or not app_running or stop_event.is_set():
                return
            for item in primary_tree.get_children():
                primary_tree.delete(item)
            for item in extended_tree.get_children():
                extended_tree.delete(item)
            sorted_ips = sorted(entries, key=lambda x: tuple(int(p) for p in x.split(".")))
            for ip_addr in sorted_ips:
                name, mac, is_primary = entries[ip_addr]
                tree = primary_tree if is_primary else extended_tree
                tag = ("own",) if ip_addr == own_ip else ()
                tree.insert("", "end", values=(ip_addr, name, mac), tags=tag)
            primary_tree.tag_configure("own", background="#FFE0B2")
            extended_tree.tag_configure("own", background="#FFE0B2")
            if progress_label is not None:
                progress_label.config(text=f"Scan abgeschlossen. {len(entries)} Geräte gefunden.")
            if progress_bar is not None:
                progress_bar.config(value=progress_bar.cget("maximum"))
            if on_scan_done:
                on_scan_done()

        try:
            root.after(0, insert_entries)
        except:
            pass

    threading.Thread(target=worker, daemon=True).start()

NETWORK_BACKUP_FILE = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "network_backup.json")


def find_kasse_version_path():
    for parent in (r"C:\X3000", r"C:\\"):
        try:
            for name in os.listdir(parent):
                if name.lower().startswith("kasse"):
                    folder = os.path.join(parent, name)
                    if os.path.isdir(folder):
                        version_file = os.path.join(folder, "VERSION.TXT")
                        if os.path.isfile(version_file):
                            return version_file
        except OSError:
            continue
    return None


def get_kasse_version():
    path = find_kasse_version_path()
    if not path:
        return "Keine Versionsinformationen gefunden"
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    except OSError:
        return "Keine Versionsinformationen gefunden"


def get_kasse_install_datum():
    path = find_kasse_version_path()
    if not path:
        return "Nicht verfügbar"
    try:
        stat = os.stat(path)
        installed_ts = max(stat.st_ctime, stat.st_mtime)
        return datetime.fromtimestamp(installed_ts).strftime("%d.%m.%Y")
    except OSError:
        return "Nicht verfügbar"


def resolve_kasse_dir(parent_dir):
    exact = os.path.join(parent_dir, "kasse")
    if os.path.isdir(exact):
        return exact
    try:
        matches = sorted(
            os.path.join(parent_dir, name)
            for name in os.listdir(parent_dir)
            if name.lower().startswith("kasse")
            and os.path.isdir(os.path.join(parent_dir, name))
        )
        return matches[0] if matches else None
    except OSError:
        return None


def scan_ws_folders(base_dir, ws_pattern):
    numbers = []
    for name in os.listdir(base_dir):
        folder_path = os.path.join(base_dir, name)
        if not os.path.isdir(folder_path):
            continue
        match = ws_pattern.match(name)
        if match:
            numbers.append(match.group(1))
    return numbers


def get_entries_snapshot(entries):
    return {
        "ip": entries["IP"].get().strip(),
        "subnet": entries["Subnetz"].get().strip(),
        "gateway": entries["Gateway"].get().strip(),
        "dns1": entries["DNS1"].get().strip(),
        "dns2": entries["DNS2"].get().strip(),
        "ip_ext1": entries["IP_EXT1"].get().strip(),
        "ip_ext2": entries["IP_EXT2"].get().strip(),
        "sub_ext1": entries["Subnetz_EXT1"].get().strip(),
        "sub_ext2": entries["Subnetz_EXT2"].get().strip(),
    }


def fill_entries_from_snapshot(entries, snapshot):
    field_map = {
        "IP": "ip",
        "Subnetz": "subnet",
        "Gateway": "gateway",
        "DNS1": "dns1",
        "DNS2": "dns2",
        "IP_EXT1": "ip_ext1",
        "IP_EXT2": "ip_ext2",
        "Subnetz_EXT1": "sub_ext1",
        "Subnetz_EXT2": "sub_ext2",
    }
    for field, key in field_map.items():
        entries[field].delete(0, tk.END)
        entries[field].insert(0, snapshot.get(key, ""))


def save_network_backup(entries, was_dhcp):
    data = get_entries_snapshot(entries)
    data["dhcp"] = "Ja" if was_dhcp else "Nein"
    with open(NETWORK_BACKUP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    try:
        ctypes.windll.kernel32.SetFileAttributesW(NETWORK_BACKUP_FILE, 2)
    except:
        pass


def load_network_backup():
    try:
        with open(NETWORK_BACKUP_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


#########################################
# KASSEN-DATEN AUSLESEN
# Sucht nach dem Kassenordner (C:\X3000\Kasse-*)
# und listet die Arbeitsstationen (WSxxx) auf.
#########################################
def get_kasse_data():
    ws_pattern = re.compile(r"^WS(\d{3})$", re.IGNORECASE)

    for parent_dir in (r"C:\X3000", r"C:\\"):
        base_dir = resolve_kasse_dir(parent_dir)
        if not base_dir:
            continue
        try:
            numbers = scan_ws_folders(base_dir, ws_pattern)
        except OSError:
            continue
        if numbers:
            numbers.sort()
            return base_dir, ", ".join(numbers)

    return None, "Keine Arbeitsstationen gefunden."


def find_pg_restore():
    try:
        result = subprocess.run(["pg_restore", "--version"], capture_output=True, **_subprocess_kwargs())
        if result.returncode == 0:
            return "pg_restore"

    except:
        pass


#########################################
# FIRMENDATEN AUS PSQL-DUMPS EXTRAHIEREN
# Durchsucht die PSQL-Ordner nach SQL-Dumps und
# extrahiert Firmenname, PLZ, Ort etc. aus der
# Tabelle "kafasql" (Spalte 8 = Ort, 10 = Betrieb).
#########################################
def extract_firma_data(kasse_ordner):
    if not kasse_ordner:
        return None, "Kein Kassenordner gefunden."

    psql_dir = os.path.join(kasse_ordner, "PSQL")
    if not os.path.isdir(psql_dir):
        return None, "Kein PSQL-Unterordner gefunden."

    sql_files = [f for f in os.listdir(psql_dir) if f.lower().endswith(".sql")]
    if not sql_files:
        return None, "Keine SQL-Dateien gefunden."
    sql_files.sort(key=lambda f: os.path.getsize(os.path.join(psql_dir, f)), reverse=True)

    target_cols = ["faort", "fabetrieb", "fafirmaadresse", "fafirmaplz",
                   "falocationname", "falocationadresse", "falocationplz", "falocationort"]

    for sql_file in sql_files:
        sql_path = os.path.join(psql_dir, sql_file)
        temp_out = os.path.join(os.environ.get("TEMP", "."), f"kd_kafasql_{os.getpid()}.sql")
        try:
            pg_restore = find_pg_restore()
            if pg_restore:
                result = subprocess.run(
                    [pg_restore, "-f", temp_out, sql_path],
                    capture_output=True, timeout=120,
                    **_subprocess_kwargs(),
                )
                if result.returncode != 0 or not os.path.isfile(temp_out):
                    continue
                src = temp_out
            else:
                src = sql_path

            with open(src, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            idx = content.find("COPY x3000.kafasql (")
            if idx < 0:
                idx = content.find("COPY x3000demo.kafasql (")
            if idx < 0:
                idx = content.find("kafasql (")
                if idx >= 0:
                    copy_start = content.rfind("COPY ", 0, idx)
                    if copy_start >= 0:
                        idx = copy_start
                    else:
                        idx = -1
            if idx < 0:
                continue

            end_header = content.find(") FROM stdin;", idx)
            header = content[idx + content[idx:].find("(") + 1:end_header]
            cols = [c.strip() for c in header.split(",")]

            col_indices = {}
            for target in target_cols:
                try:
                    col_indices[target] = cols.index(target)
                except ValueError:
                    pass
            if "fabetrieb" not in col_indices:
                continue

            data_start = content.find("FROM stdin;\n", idx) + len("FROM stdin;\n")
            data_end = content.find("\n\\.\n", data_start)
            data_block = content[data_start:data_end].strip()
            first_row = data_block.split("\n")[0]
            fields = first_row.split("\t")

            result = {}
            for target, i in col_indices.items():
                result[target] = fields[i].strip() if i < len(fields) else ""

            if result.get("fabetrieb"):
                return result, None
        except Exception:
            continue
        finally:
            try:
                if os.path.isfile(temp_out):
                    os.remove(temp_out)
            except OSError:
                pass

    return None, "Firmendaten konnten nicht ausgelesen werden."


TEAMVIEWER_CANDIDATES = (
    r"C:\Program Files\TeamViewer\TeamViewer.exe",
    r"C:\Program Files (x86)\TeamViewer\TeamViewer.exe",
)
TEAMVIEWER_QS_URL = "https://download.teamviewer.com/download/TeamViewerQS_de-agmy.exe"
TEAMVIEWER_QS_FILENAME = "TeamViewerQS_de-agmy.exe"


#########################################
# PRÜFT INTERNETVERBINDUNG
# Einfacher Ping-Test zu einem DNS-Server.
#########################################
def has_internet():
    return "OK" in internet_status()


def find_teamviewer_exe():
    for path in TEAMVIEWER_CANDIDATES:
        if os.path.isfile(path):
            return path
    for base in (
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
    ):
        if not base:
            continue
        exe = os.path.join(base, "TeamViewer", "TeamViewer.exe")
        if os.path.isfile(exe):
            return exe
    return None


def find_anydesk_exe():
    download_dir = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "downloads")
    download_exe = os.path.join(download_dir, "AnyDesk.exe")
    if os.path.isfile(download_exe):
        return download_exe
    for base in (
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
    ):
        if not base:
            continue
        exe = os.path.join(base, "AnyDesk", "AnyDesk.exe")
        if os.path.isfile(exe):
            return exe
    return None


def get_anydesk_id():
    exe = find_anydesk_exe()
    if not exe:
        return "Nicht verfügbar"
    try:
        result = subprocess.run(
            [exe, "--get-id"], capture_output=True, text=True, timeout=5,
            **_subprocess_kwargs(),
        )
        out = result.stdout.strip()
        return out if out else "Nicht verfügbar"
    except Exception:
        return "Nicht verfügbar"


def get_teamviewer_id():
    ps = r"""
    $id = $null
    $paths = @(
        'HKLM:\SOFTWARE\WOW6432Node\TeamViewer',
        'HKLM:\SOFTWARE\TeamViewer'
    )
    foreach ($p in $paths) {
        if (Test-Path $p) {
            $val = (Get-ItemProperty -Path $p -Name ClientID -ErrorAction SilentlyContinue).ClientID
            if ($val) { $id = $val; break }
            $val = (Get-ItemProperty -Path $p -Name ClientID_0 -ErrorAction SilentlyContinue).ClientID_0
            if ($val) { $id = $val; break }
        }
    }
    if (-not $id) {
        $iniPaths = @(
            "$env:ProgramFiles\TeamViewer\TeamViewer.ini",
            "${env:ProgramFiles(x86)}\TeamViewer\TeamViewer.ini"
        )
        foreach ($ini in $iniPaths) {
            if (Test-Path $ini) {
                $content = Get-Content $ini -ErrorAction SilentlyContinue
                foreach ($line in $content) {
                    if ($line -match 'ClientID\s*=\s*(\d+)') { $id = $matches[1]; break }
                }
            }
            if ($id) { break }
        }
    }
    if ($id) { Write-Output $id } else { Write-Output "" }
    """
    try:
        id_ = run_powershell(ps, bypass_policy=True).strip()
        return id_ if id_ else "Nicht verfügbar"
    except Exception:
        return "Nicht verfügbar"


def winget_available():
    try:
        result = subprocess.run(
            ["winget", "--version"],
            capture_output=True,
            **_subprocess_kwargs(),
        )
        return result.returncode == 0
    except (FileNotFoundError, OSError):
        return False


def install_teamviewer_winget():
    return subprocess.run(
        [
            "winget",
            "install",
            "--id",
            "TeamViewer.TeamViewer",
            "-e",
            "--silent",
            "--accept-package-agreements",
            "--accept-source-agreements",
        ],
        **_subprocess_kwargs(),
    )


def download_and_run_teamviewer_quicksupport():
    if not has_internet():
        return False, "❌ Keine Internetverbindung – Download nicht möglich."

    download_dir = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "downloads")
    os.makedirs(download_dir, exist_ok=True)
    target = os.path.join(download_dir, TEAMVIEWER_QS_FILENAME)

    try:
        request = urllib.request.Request(TEAMVIEWER_QS_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=120) as response, open(target, "wb") as out_file:
            out_file.write(response.read())
    except Exception as exc:
        return False, f"❌ Download fehlgeschlagen. {benutzer_fehlermeldung(exc)}"

    try:
        os.startfile(target)
        return True, "✅ TeamViewer QuickSupport wurde heruntergeladen und gestartet."
    except OSError as exc:
        return False, f"❌ Heruntergeladene Datei konnte nicht gestartet werden. {benutzer_fehlermeldung(exc)}"


def open_teamviewer():
    exe = find_teamviewer_exe()
    if exe:
        os.startfile(exe)
        return True, "✅ TeamViewer wurde geöffnet."

    if not has_internet():
        return (
            False,
            "❌ Keine Internetverbindung – TeamViewer ist nicht installiert. "
            "Download und Installation sind nicht möglich.",
        )

    if winget_available():
        install_teamviewer_winget()
        exe = find_teamviewer_exe()
        if exe:
            os.startfile(exe)
            return True, "✅ TeamViewer wurde installiert und geöffnet."

    return download_and_run_teamviewer_quicksupport()


ANYDESK_URL = "https://download.anydesk.com/AnyDesk.exe"


def install_anydesk_winget():
    result = subprocess.run(
        [
            "winget",
            "install",
            "-e",
            "--id",
            "AnyDesk.AnyDesk",
            "--silent",
            "--accept-package-agreements",
            "--accept-source-agreements",
        ],
        **_subprocess_kwargs(),
    )
    return result.returncode == 0


def download_and_run_anydesk():
    download_dir = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "downloads")
    os.makedirs(download_dir, exist_ok=True)
    target = os.path.join(download_dir, "AnyDesk.exe")

    if os.path.isfile(target):
        try:
            os.startfile(target)
            return True, "✅ AnyDesk wurde geöffnet."
        except OSError as exc:
            return False, f"❌ AnyDesk konnte nicht gestartet werden. {benutzer_fehlermeldung(exc)}"

    if not has_internet():
        return False, "❌ Keine Internetverbindung – Download nicht möglich."

    try:
        request = urllib.request.Request(ANYDESK_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=120) as response, open(target, "wb") as out_file:
            out_file.write(response.read())
    except Exception as exc:
        return False, f"❌ Download fehlgeschlagen. {benutzer_fehlermeldung(exc)}"

    try:
        os.startfile(target)
        return True, "✅ AnyDesk wurde heruntergeladen und gestartet."
    except OSError as exc:
        return False, f"❌ Heruntergeladene Datei konnte nicht gestartet werden. {benutzer_fehlermeldung(exc)}"


def open_anydesk():
    exe = find_anydesk_exe()
    if exe:
        os.startfile(exe)
        return True, "✅ AnyDesk wurde geöffnet."

    if not has_internet():
        return (
            False,
            "❌ Keine Internetverbindung – AnyDesk ist nicht installiert. "
            "Download und Installation sind nicht möglich.",
        )

    if winget_available() and install_anydesk_winget():
        exe = find_anydesk_exe()
        if exe:
            os.startfile(exe)
            return True, "✅ AnyDesk wurde installiert und geöffnet."

    return download_and_run_anydesk()


def get_text_output_path(kasse_firma_data=None):
    date_str = datetime.now().strftime("%d.%m.%Y")
    folder = os.path.dirname(os.path.abspath(sys.argv[0]))
    f_name = (kasse_firma_data or {}).get("fabetrieb", "").strip()
    f_plz = (kasse_firma_data or {}).get("fafirmaplz", "").strip()
    f_ort = (kasse_firma_data or {}).get("faort", "").strip()
    f_plzort = " ".join(p for p in [f_plz, f_ort] if p)
    f_parts = ", ".join(p for p in [f_name, f_plzort] if p)
    stem = f"PC-Informationen - {f_parts} - {socket.gethostname()}, {date_str}" if f_parts else f"PC-Informationen - {socket.gethostname()}, {date_str}"
    safe = "".join(c for c in stem if c not in r'\/:*?"<>|')
    return os.path.join(folder, f"{safe}.txt")


def get_uptime_str():
    ps = r"""
    $boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
    $now = Get-Date
    $uptime = $now - $boot
    $bootStr = $boot.ToString('dd.MM.yyyy HH:mm')
    $uptimeStr = "$($uptime.Days) Tage, $($uptime.Hours) Stunden, $($uptime.Minutes) Minuten"
    Write-Output "$bootStr|$uptimeStr"
    """
    try:
        out = run_powershell(ps, bypass_policy=True).strip()
        parts = out.split("|")
        if len(parts) == 2:
            return parts[0], parts[1]
    except Exception:
        pass
    return "Unbekannt", "Unbekannt"


def get_drive_info():
    ps = r"""
    Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Used -and $_.Free -and $_.Name -match '^[A-Z]$' } |
    ForEach-Object {
        $total = [math]::Round(($_.Used + $_.Free) / 1GB, 1)
        $used  = [math]::Round($_.Used / 1GB, 1)
        $pct   = [math]::Round(($_.Used / ($_.Used + $_.Free)) * 100, 0)
        "$($_.Name)|$total GB|$used GB|$pct%"
    }
    """
    try:
        out = run_powershell(ps).strip()
        return [line.strip() for line in out.splitlines() if "|" in line] if out else []
    except Exception:
        return []


def get_local_users():
    try:
        out = run_powershell("Get-LocalUser | Select-Object -ExpandProperty Name").strip()
        return [u.strip() for u in out.splitlines() if u.strip()]
    except Exception:
        return []


def create_pc_infos_text(report_data):
    lines = []
    sep = "=" * 70

    lines.append(sep)
    lines.append("  Keller & Duerr - PC Informationen")
    lines.append(sep)
    lines.append(f"  Erstellt am:  {report_data['erstellt_am']}")
    lines.append(f"  Administrator: {'Ja' if report_data['admin'] else 'Nein'}")
    lines.append("")

    sections = [
        ("FIRMA", report_data["kasse_firma"], "firma"),
        ("BETRIEBSSTAETTE", report_data["kasse_betriebsstaette"], "firma"),
        ("NETZWERKEINSTELLUNGEN", report_data["netzwerkeinstellungen"], "label"),
        ("NETZWERKEINSTELLUNGEN (EINGABEN)", report_data["netzwerk_eingaben"], "label"),
        ("WINDOWS", report_data["windows"], "label"),
        ("BENUTZER", report_data["benutzer"], "users"),
        ("DRUCKER", report_data["drucker"], "printer"),
        ("NETZWERKGERAETE", report_data["vlan"], "vlan"),
        ("DATENTRAEGER", report_data["datentraeger"], "drives"),
        ("KASSE", report_data["kasse"], "label"),
        ("INTERNET", None, "internet"),
        ("TEAMVIEWER", None, "tv"),
        ("ANYDESK", None, "anydesk"),
    ]

    for title, data, dtype in sections:
        lines.append(sep)
        lines.append(f"  {title}")
        lines.append(sep)
        if dtype == "label":
            for label, value in data:
                lines.append(f"    {label:<24}  {value}")
        elif dtype == "users":
            if data:
                for u in data:
                    lines.append(f"    {u}")
            else:
                lines.append("    Keine Benutzer gefunden")
        elif dtype == "drives":
            if data:
                for d in data:
                    parts = d.split("|")
                    if len(parts) >= 4:
                        lines.append(f"    Laufwerk {parts[0]}:  {parts[2]} von {parts[1]} belegt ({parts[3]})")
            else:
                lines.append("    Keine Laufwerksdaten")
        elif dtype == "printer":
            if data:
                for entry in data:
                    name, ip = entry[0], entry[1]
                    lines.append(f"    {name:<32}  {ip}")
            else:
                lines.append("    Keine Drucker gefunden")
        elif dtype == "vlan":
            if data:
                for ip, name, mac in data:
                    lines.append(f"    {ip:<18}  {name:<30}  {mac}")
            else:
                lines.append("    Keine Geraete gefunden")
        elif dtype == "firma":
            name = data.get("firma_name") or data.get("bs_name")
            strasse = data.get("firma_strasse") or data.get("bs_adresse")
            plzort = data.get("firma_plzort") or data.get("bs_plzort")
            if name and hasattr(name, "cget"):
                lines.append(f"    {'Name':<24}  {name.cget('text')}")
                lines.append(f"    {'Strasse':<24}  {strasse.cget('text')}")
                lines.append(f"    {'PLZ/Ort':<24}  {plzort.cget('text')}")
        elif dtype == "internet":
            lines.append(f"    Status{'':>20}  {report_data['internet']}")
        elif dtype == "tv":
            lines.append(f"    {report_data['teamviewer']}")
        elif dtype == "anydesk":
            lines.append(f"    {report_data['anydesk']}")
        lines.append("")

    lines.append(sep)

    output_path = report_data["output_path"]
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return output_path


def create_system_info_text(report_data):
    output_dir = os.path.dirname(report_data["output_path"])
    output_path = os.path.join(output_dir, "Systeminformationen.txt")
    try:
        _si = subprocess.STARTUPINFO()
        _si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        _si.wShowWindow = subprocess.SW_HIDE
        subprocess.run(
            ["msinfo32", "/report", output_path],
            startupinfo=_si, timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
    except:
        pass
    return output_path


# =========================================================
# LADE-GUI
# =========================================================
#########################################
# FENSTER-ANIMATIONEN
# Lässt Fenster beim Einblenden von oben
# hereingleiten (Slide-In-Effekt).
#########################################
def center_window(window, width, height):
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x = (screen_width - width) // 2
    y = (screen_height - height) // 2
    window.geometry(f"{width}x{height}+{x}+{y}")


def slide_in(window, width, height, speed=60, interval=5):
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x = (screen_width - width) // 2
    target_y = (screen_height - height) // 2
    window.geometry(f"{width}x{height}+{x}+{-height}")
    window.deiconify()
    window.update_idletasks()
    state = {"y": -height}

    def animate():
        state["y"] += speed
        if state["y"] >= target_y:
            window.geometry(f"+{x}+{target_y}")
            return
        window.geometry(f"+{x}+{state['y']}")
        window.after(interval, animate)

    animate()


def slide_out(window, speed=60, interval=5, on_done=None):
    try:
        x = window.winfo_x()
        screen_height = window.winfo_screenheight()
    except tk.TclError:
        if on_done: on_done()
        return
    state = {"y": window.winfo_y()}

    def animate():
        state["y"] += speed
        if state["y"] >= screen_height:
            if on_done:
                on_done()
            else:
                try: window.destroy()
                except tk.TclError: pass
            return
        try:
            window.geometry(f"+{x}+{state['y']}")
            window.after(interval, animate)
        except tk.TclError:
            if on_done: on_done()

    animate()
#########################################
# START-BILDSCHIRM (SPLASH)
# Zeigt beim Programmstart ein Fenster mit Ladebalken.
# Lädt im Hintergrund alle Daten:
# - Netzwerk, Drucker, Internet, Windows, Kasse
# - Firewall-Status, Firmendaten
# Nach dem Laden wird die Haupt-GUI gestartet.
#########################################
def show_loading_gui():
    state_file = os.path.join(tempfile.gettempdir(), "kdtool_state.json")
    try:
        with open(state_file) as f:
            state = json.load(f)
        checked = state.get("checked", False)
        password_ok = state.get("pw_ok", False)
        os.remove(state_file)
    except:
        checked = False
        password_ok = False
    splash_version = "260529"

    root = tk.Tk()
    _icon_path = os.path.join(_exe_dir, "KDtool.ico")
    if getattr(sys, 'frozen', False):
        _mei_icon = os.path.join(sys._MEIPASS, "KDtool.ico")
        if os.path.isfile(_mei_icon):
            _icon_path = _mei_icon
    if os.path.isfile(_icon_path):
        try:
            root.iconbitmap(bitmap=_icon_path)
        except Exception:
            pass
    root.withdraw()
    root.title(f"KDtool v{splash_version} - Keller & Dürr Kassensysteme AG")
    root.configure(bg="white")
    root.resizable(True, True)
    def _tk_exc_handler(exc, val, tb):
        with open(_log_file, "a") as _f:
            _f.write(f"=== {_time.strftime('%Y-%m-%d %H:%M:%S')} TKINTER CALLBACK ERROR ===\n")
            traceback.print_exception(exc, val, tb, file=_f)
            _f.write("\n")
    root.report_callback_exception = _tk_exc_handler

    if not is_admin() or not checked:
        dialog = tk.Toplevel(root)
        if os.path.isfile(_icon_path):
            try:
                dialog.iconbitmap(bitmap=_icon_path)
            except Exception:
                pass
        dialog.withdraw()
        dialog.title(f"KDtool v{splash_version} - Keller & Dürr Kassensysteme AG")
        dialog.configure(bg="white")
        dialog.resizable(False, False)

        tk.Label(
            dialog,
            text="KDtool",
            font=("Segoe UI", 14, "bold"),
            fg="#0078d4", bg="white",
        ).pack(pady=(25, 2))

        tk.Label(
            dialog,
            text="Keller & Dürr Kassensysteme AG",
            font=("Segoe UI", 11),
            fg="#0078d4", bg="white",
        ).pack(pady=(0, 12))

        pw_ok = [False]
        restart = [False]

        if is_admin():
            def on_start():
                now = datetime.now()
                pw_ok[0] = password_entry.get() == f"{now.month + 1:02d}{now.day + 1:02d}"
                slide_out(dialog, on_done=dialog.destroy)

            btn_frame = tk.Frame(dialog, bg="white")
            btn_frame.pack(pady=(15, 0))
            tk.Button(
                btn_frame, text="Starten …", width=12, height=1,
                bg="#0078d4", fg="white", font=("Segoe UI", 10, "bold"),
                relief="flat", command=on_start,
            ).pack()
        else:
            tk.Label(
                dialog,
                text="Keine Administrator-Rechte erkannt.",
                font=("Segoe UI", 11),
                fg="#333333", bg="white",
            ).pack()
            tk.Label(
                dialog,
                text="Mit Administrator-Rechten neu starten?",
                font=("Segoe UI", 11),
                fg="#333333", bg="white",
            ).pack(pady=(0, 8))

            def on_yes():
                now = datetime.now()
                pw_ok[0] = password_entry.get() == f"{now.month + 1:02d}{now.day + 1:02d}"
                restart[0] = True
                slide_out(dialog, on_done=dialog.destroy)

            def on_no():
                now = datetime.now()
                pw_ok[0] = password_entry.get() == f"{now.month + 1:02d}{now.day + 1:02d}"
                slide_out(dialog, on_done=dialog.destroy)

            btn_frame = tk.Frame(dialog, bg="white")
            btn_frame.pack(pady=(15, 0))
            ja_btn = tk.Button(
                btn_frame, text="Ja", width=12, height=1,
                bg="#0078d4", fg="white", font=("Segoe UI", 10, "bold"),
                relief="flat", command=on_yes,
            )
            ja_btn.pack(side="left", padx=(0, 10))
            tk.Button(
                btn_frame, text="Nein", width=12, height=1,
                bg="#6c757d", fg="white", font=("Segoe UI", 10, "bold"),
                relief="flat", command=on_no,
            ).pack(side="left")

            countdown = [10]
            timer_active = [True]

            def _tick():
                if not timer_active[0]:
                    return
                countdown[0] -= 1
                if countdown[0] <= 0:
                    on_yes()
                else:
                    ja_btn.config(text=f"Ja ({countdown[0]})")
                    dialog.after(1000, _tick)

            def _stop_timer(*args):
                if timer_active[0]:
                    timer_active[0] = False
                    ja_btn.config(text="Ja")

        pw_frame = tk.Frame(dialog, bg="white")
        pw_frame.pack(pady=(8, 0))
        tk.Label(pw_frame, text="K&D Servicepasswort:", font=("Segoe UI", 10), fg="#444444", bg="white").pack(side="left", padx=(0, 8))
        password_entry = tk.Entry(pw_frame, width=6, font=("Segoe UI", 12, "bold"), show="\u25CF", justify="center",
                                  relief="solid", bd=1)

        if not is_admin():
            password_entry.bind("<KeyRelease>", _stop_timer)
            dialog.after(1000, _tick)
        password_entry.pack(side="left")

        def _on_dialog_shown():
            password_entry.focus_set()
            password_entry.focus_force()
            dialog.after(50, password_entry.focus_set)

        dialog.bind("<Map>", lambda e: dialog.after(10, _on_dialog_shown))

        tk.Label(
            dialog,
            text="Die Keller & Dürr Kassensysteme AG übernimmt keine Haftung für Schäden, "
                 "die durch unsachgemässe oder fehlerhafte Anwendung dieser Software entstehen.",
            font=("Segoe UI", 7),
            fg="#999999", bg="white", wraplength=480, justify="center",
        ).pack(side="bottom", pady=(0, 12))

        if is_admin():
            dialog.bind("<Return>", lambda e: on_start())
        else:
            dialog.bind("<Return>", lambda e: on_yes())
        slide_in(dialog, 520, 320)
        set_titlebar_style(dialog)
        dialog.wait_window()

        if restart[0]:
            with open(state_file, "w") as f:
                json.dump({"checked": True, "pw_ok": pw_ok[0]}, f)
            restart_as_admin()
            return

        password_ok = pw_ok[0]

    splash = tk.Toplevel(root)
    if os.path.isfile(_icon_path):
        try:
            splash.iconbitmap(bitmap=_icon_path)
        except Exception:
            pass
    splash.withdraw()
    splash.title(f"KDtool v{splash_version} - Keller & Dürr Kassensysteme AG")
    splash.configure(bg="white")
    splash.resizable(False, False)

    tk.Label(
        splash,
        text="KDtool",
        font=("Segoe UI", 16, "bold"),
        fg="#0078d4",
        bg="white",
    ).pack(pady=(40, 2))

    tk.Label(
        splash,
        text="Keller & Dürr Kassensysteme AG",
        font=("Segoe UI", 12),
        fg="#0078d4",
        bg="white",
    ).pack(pady=(0, 10))

    splash_label = tk.Label(
        splash,
        text="Daten werden abgerufen, bitte warten...",
        font=("Segoe UI", 11),
        fg="#555555",
        bg="white",
    )
    splash_label.pack(pady=(0, 20))

    style = ttk.Style()
    style.theme_use("clam")
    style.configure("blue.Horizontal.TProgressbar", background="#0078d4")
    progress = ttk.Progressbar(splash, style="blue.Horizontal.TProgressbar", mode="determinate", maximum=100, length=400)
    progress.pack(pady=10)

    loaded = {"network": None, "dhcp": None, "printers": None, "internet": None,
              "windows": None, "kasse_version": None, "kasse_install_datum": None,
              "last_windows_update": None, "kasse_ordner": None, "arbeitsstationen": None,
              "boot_time": None, "uptime_str": None, "tv_id": None, "anydesk_id": None,
              "kasse_firma_data": None, "firewall": None}
    load_steps = [
        ("network", get_network),
        ("dhcp", get_dhcp_status),
        ("printers", get_printers),
        ("internet", internet_status),
        ("windows", windows_info),
        ("kasse_version", get_kasse_version),
        ("kasse_install_datum", get_kasse_install_datum),
        ("last_windows_update", get_last_windows_update),
        ("tv_id", get_teamviewer_id),
        ("anydesk_id", get_anydesk_id),
        ("firewall", get_firewall_status),
    ]

    def update_progress(value):
        progress["value"] = value
        splash.update_idletasks()

    def finish_loading():
        def on_slide_done():
            splash.destroy()
            start_gui(root,
                net=loaded["network"],
                dhcp=loaded["dhcp"],
                printers=loaded["printers"],
                internet=loaded["internet"],
                windows=loaded["windows"],
                kasse_version=loaded["kasse_version"],
                kasse_install_datum=loaded["kasse_install_datum"],
                kasse_ordner=loaded["kasse_ordner"],
                arbeitsstationen=loaded["arbeitsstationen"],
                last_windows_update=loaded["last_windows_update"],
                boot_time=loaded["boot_time"],
                uptime_str=loaded["uptime_str"],
                tv_id=loaded["tv_id"],
                anydesk_id=loaded["anydesk_id"],
                password_ok=password_ok,
                kasse_firma_data=loaded["kasse_firma_data"],
                firewall=loaded["firewall"],
                version_str=splash_version,
            )
        slide_out(splash, on_done=on_slide_done)

    def load_worker():
        total = len(load_steps)
        for i, (key, loader) in enumerate(load_steps):
            loaded[key] = loader()
            pct = int((i + 1) / total * 100)
            splash.after(0, update_progress, pct)
        loaded["kasse_ordner"], loaded["arbeitsstationen"] = get_kasse_data()
        firma_result, _ = extract_firma_data(loaded["kasse_ordner"])
        loaded["kasse_firma_data"] = firma_result
        loaded["boot_time"], loaded["uptime_str"] = get_uptime_str()

        splash.after(0, finish_loading)

    def _safe_load_worker():
        try:
            load_worker()
        except Exception:
            with open(_log_file, "a") as _f:
                _f.write(f"=== {_time.strftime('%Y-%m-%d %H:%M:%S')} load_worker ERROR ===\n")
                traceback.print_exc(file=_f)
                _f.write("\n")

    threading.Thread(target=_safe_load_worker, daemon=True).start()
    slide_in(splash, 520, 220)
    set_titlebar_style(splash)
    try:
        root.mainloop()
    except Exception:
        with open(_log_file, "a") as _f:
            _f.write(f"=== {_time.strftime('%Y-%m-%d %H:%M:%S')} MAINLOOP ERROR ===\n")
            traceback.print_exc(file=_f)
            _f.write("\n")



# =========================================================
# GUI
# =========================================================
#########################################
# GUI-HILFSFUNKTIONEN
# Einfache Bausteine für die Benutzeroberfläche:
# Info-Zeilen, Bereichsüberschriften, IP-Anzeigen.
#########################################
def add_info_row(parent, label, value, value_fg="#000000", label_width=14):
    row = tk.Frame(parent, bg="white")
    row.pack(fill="x", padx=30, pady=8)
    tk.Label(
        row, text=f"{label}:", width=label_width, anchor="w", bg="white", fg="#444444", font=("Segoe UI", 10)
    ).pack(side="left")
    value_label = tk.Label(
        row, text=value, anchor="w", bg="white", fg=value_fg, font=("Segoe UI", 10, "bold"), justify="left"
    )
    value_label.pack(side="left", fill="x", expand=True)
    return value_label


def add_section_title(parent, text, top_padding=25, on_refresh=None):
    header = tk.Frame(parent, bg="white")
    header.pack(fill="x", padx=30, pady=(top_padding, 5))
    tk.Label(header, text=text, font=("Segoe UI", 13, "bold"), fg="#0078d4", bg="white").pack(side="left")
    if on_refresh:
        tk.Button(header, text="↻ Aktualisieren", font=("Segoe UI", 9), bg="#0078d4", fg="white",
                  relief="flat", padx=10, pady=2, command=on_refresh).pack(side="right")
    return header


def add_ip_address_row(parent, primary_ip, extended_ips=""):
    ip_row = tk.Frame(parent, bg="white")
    ip_row.pack(fill="x", padx=30, pady=8)
    tk.Label(
        ip_row, text="IP-Adresse:", width=22, anchor="w", bg="white", fg="#444444", font=("Segoe UI", 10)
    ).pack(side="left")
    ip_val = tk.Label(
        ip_row, text=primary_ip, anchor="w", bg="white", fg="#000000", font=("Segoe UI", 10, "bold")
    )
    ip_val.pack(side="left", fill="x", expand=True)

    ext_row = tk.Frame(parent, bg="white")
    tk.Label(
        ext_row, text="Erweiterte Netzwerke:", width=22, anchor="w", bg="white", fg="#444444", font=("Segoe UI", 10)
    ).pack(side="left", anchor="n")
    ext_text = "\n".join(e.strip() for e in extended_ips.split(",") if e.strip()) if extended_ips else ""
    ext_val = tk.Label(
        ext_row, text=ext_text, anchor="w", bg="white", fg="#333333", font=("Segoe UI", 10), justify="left"
    )
    ext_val.pack(side="left", fill="x", expand=True)
    if extended_ips:
        ext_row.pack(fill="x", padx=30, pady=(0, 8))

    return {"primary": ip_val, "extended": ext_val, "ext_row": ext_row}


def update_ip_address_row(ip_labels, primary_ip, extended_ips="", before_widget=None):
    ip_labels["primary"].config(text=primary_ip)
    if extended_ips:
        ext_text = "\n".join(e.strip() for e in extended_ips.split(",") if e.strip())
        ip_labels["extended"].config(text=ext_text)
        kwargs = {"fill": "x", "padx": 30, "pady": (0, 8)}
        if before_widget:
            kwargs["before"] = before_widget
        ip_labels["ext_row"].pack(**kwargs)
    else:
        ip_labels["ext_row"].pack_forget()


def add_kasse_ordner_row(parent, folder_path):
    row = tk.Frame(parent, bg="white")
    row.pack(fill="x", padx=30, pady=8)
    tk.Label(
        row, text="Kassenordner:", width=14, anchor="w", bg="white", fg="#444444", font=("Segoe UI", 10)
    ).pack(side="left")
    display_path = folder_path if folder_path else "Nicht gefunden"
    val = tk.Label(
        row, text=display_path, anchor="w", bg="white", fg="#000000", font=("Segoe UI", 10, "bold")
    )
    val.pack(side="left")
    tk.Button(
        row,
        text="öffnen",
        bg="#0078d4",
        fg="white",
        font=("Segoe UI", 9, "bold"),
        relief="flat",
        padx=12,
        pady=2,
        command=lambda: os.startfile(folder_path) if folder_path and os.path.isdir(folder_path) else None,
        state="normal" if folder_path and os.path.isdir(folder_path) else "disabled",
    ).pack(side="left", padx=10)
    return val


def start_gui(root, net, dhcp, printers, internet, windows, kasse_version, kasse_install_datum,
              kasse_ordner, arbeitsstationen, last_windows_update, boot_time, uptime_str, tv_id, anydesk_id,
              password_ok=True, kasse_firma_data=None, firewall=None, version_str="260529"):
    global app_running

    root.title(f"KDtool v{version_str} - Keller & Dürr Kassensysteme AG")
    root.configure(bg="white")

    style = ttk.Style()
    style.theme_use("clam")

    style.configure("TNotebook", background="white")
    style.configure("TFrame", background="white")
    style.configure("TLabel", background="white", foreground="#333333")
    style.configure("Treeview", background="white", fieldbackground="white", foreground="#222222", rowheight=28)
    style.configure("Treeview.Heading", background="#0078d4", foreground="white", font=("Segoe UI", 10, "bold"))
    style.map("Treeview.Heading", background=[("active", "#005a9e")])

    tab_bar = tk.Frame(root, bg="white")
    tab_bar.pack(fill="x", padx=10, pady=(5, 0))
    tab_bar.grid_rowconfigure(0, weight=1)

    tabs = tk.Frame(root, bg="#cccccc", bd=1, relief="solid")
    tabs.pack(fill="both", expand=True, padx=10, pady=(0, 5))

    _tab_pages = {}
    _tab_buttons = {}
    _tab_active = None
    _vlan_scan_complete = [False]
    _printer_scan_complete = [False]
    _tab_col = [0]
    _tab_busy = set()
    _cur_net = net
    _cur_dhcp = dhcp
    _cur_kasse_ordner = kasse_ordner
    _cur_kasse_ws = [arbeitsstationen]
    _cur_kasse_firma_data = kasse_firma_data
    _cur_tv_id = tv_id
    _cur_anydesk_id = anydesk_id

    def _get_tab_color(name):
        if name in _tab_busy:
            return "#FFE0B2"
        if name == "Netzwerkeinstellungen":
            ip_txt = ip_labels["primary"].cget("text")
            if ip_txt in ("Keine Verbindung", "") or ip_txt.startswith("169.254."):
                return "#EF9A9A"
            return "#C8E6C9"
        if name == "Netzwerkgeräte":
            ip_txt = ip_labels["primary"].cget("text")
            if ip_txt in ("Keine Verbindung", "") or ip_txt.startswith("169.254."):
                return "#EF9A9A"
            return "#FFE0B2" if not _vlan_scan_complete[0] else "#C8E6C9"
        if name == "Drucker":
            if not _printer_scan_complete[0]:
                return "#FFE0B2"
            return "#EF9A9A" if tree.tag_has("fehler") else "#C8E6C9"
        if name == "Windows":
            return "#C8E6C9"
        if name == "Internet":
            txt = internet_label.cget("text")
            return "#C8E6C9" if "OK" in txt else "#EF9A9A"
        if name == "Fernwartung":
            txt = internet_label.cget("text")
            if "OK" not in txt:
                return "#EF9A9A"
            cur_tv_id = tv_id_label.cget("text") if tv_id_label.cget("text") != "Nicht verfügbar" else ""
            cur_ad_id = ad_id_label.cget("text") if ad_id_label.cget("text") != "Nicht verfügbar" else ""
            found = bool(cur_tv_id or cur_ad_id)
            return "#C8E6C9" if found else "#FFE0B2"
        if name == "Kasse":
            if not _cur_kasse_ordner:
                return "#EF9A9A"
            ws = _cur_kasse_ws[0]
            if not ws or "Keine" in ws:
                return "#EF9A9A"
            return "#C8E6C9"
        if name == "Daten übermitteln":
            txt = internet_label.cget("text")
            if "OK" not in txt:
                return "#FFE0B2"
            return "#C8E6C9" if _vlan_scan_complete[0] else "#FFE0B2"
        if name == "Info":
            return "#BBDEFB"
        return "#E0E0E0"

    def _update_tab_colors():
        for name in _tab_pages:
            if name in _tab_buttons:
                btn = _tab_buttons[name]
                if name != _tab_active:
                    btn.config(bg=_get_tab_color(name))

    def _switch_tab(name):
        nonlocal _tab_active
        if _tab_active:
            _tab_pages[_tab_active].pack_forget()
            _tab_buttons[_tab_active].config(
                bg=_get_tab_color(_tab_active), fg="#333333",
                relief="raised", bd=2,
                font=("Segoe UI", 10), padx=14, pady=8)
        _tab_pages[name].pack(fill="both", expand=True)
        _tab_buttons[name].config(
            bg="#0078d4", fg="white",
            relief="raised", bd=2,
            font=("Segoe UI", 10, "bold"), padx=18, pady=14)
        _tab_active = name

    def _add_tab(page, text=""):
        _tab_pages[text] = page
        bg = _get_tab_color(text)
        btn = tk.Button(tab_bar, text=text, relief="raised", bd=2, cursor="hand2",
                        bg=bg, fg="#333333", font=("Segoe UI", 10), padx=14, pady=8,
                        command=lambda t=text: _switch_tab(t))
        btn.grid(row=0, column=_tab_col[0], sticky="s", padx=1)
        _tab_col[0] += 1
        _tab_buttons[text] = btn
        page.pack(fill="both", expand=True)
        page.pack_forget()
        if _tab_active is None:
            _switch_tab(text)

    # ====================== NETZWERKEINSTELLUNGEN ======================
    t1 = ttk.Frame(tabs)

    def apply_network_data(new_net, new_dhcp):
        nonlocal _cur_net, _cur_dhcp
        _cur_net = new_net
        _cur_dhcp = new_dhcp
        update_ip_address_row(ip_labels, new_net["ip"], new_net.get("extended_ips", ""), before_widget=info_labels["Subnetz"].master)
        info_labels["Subnetz"].config(text=new_net["subnet"])
        info_labels["Gateway"].config(text=new_net["gateway"])
        info_labels["DNS1"].config(text=new_net["dns1"] or "-")
        info_labels["DNS2"].config(text=new_net["dns2"] or "-")
        info_labels["Interface"].config(text=new_net["iface"])
        info_labels["DHCP"].config(text=new_dhcp)

        _vlan_scan_complete[0] = False
        _update_tab_colors()
        global vlan_scan_id
        for item in tree2_primary.get_children():
            tree2_primary.delete(item)
        for item in tree2_extended.get_children():
            tree2_extended.delete(item)
        vlan_progress_bar.config(value=0)
        vlan_progress_label.config(text="")
        set_report_buttons_state(False)
        if new_net.get("extended_list"):
            vlan_extended_frame.pack(fill="both", expand=True, pady=(5, 0))
        else:
            vlan_extended_frame.pack_forget()
        load_vlan(
            tree2_primary, tree2_extended, root, new_net["ip"], new_net.get("extended_list", []),
            progress_label=vlan_progress_label, progress_bar=vlan_progress_bar,
            on_scan_done=on_scan_done,
        )

    def refresh_network_display():
        def worker():
            new_net = get_network()
            new_dhcp = get_dhcp_status()
            root.after(0, lambda: (
                apply_network_data(new_net, new_dhcp),
                info_labels["PC Name"].config(text=platform.node()),
                _refresh_firewall(),
            ))

        threading.Thread(target=worker, daemon=True).start()

    refresh_top = tk.Frame(t1, bg="white")
    refresh_top.pack(fill="x", padx=30, pady=(20, 0))
    tk.Button(refresh_top, text="↻ Aktualisieren", font=("Segoe UI", 9), bg="#0078d4", fg="white",
              relief="flat", padx=10, pady=2, command=refresh_network_display).pack(side="right")

    net_content = tk.Frame(t1, bg="white")
    net_content.pack(fill="x")

    left_col = tk.Frame(net_content, bg="white")
    left_col.pack(side="left", fill="both", expand=True)

    add_section_title(left_col, "Netzwerkeinstellungen", top_padding=0)

    info_labels = {}
    info_labels["PC Name"] =     add_info_row(left_col, "PC Name", platform.node(), label_width=22)
    ip_labels = add_ip_address_row(left_col, net["ip"], net.get("extended_ips", ""))
    if net["ip"].startswith("169.254."):
        ip_labels["primary"].config(text=f'{net["ip"]} (APIPA)', fg="#d32f2f")
    for label, value in [
        ("Subnetz", net["subnet"]),
        ("Gateway", net["gateway"]),
        ("DNS1", net["dns1"] or "-"),
        ("DNS2", net["dns2"] or "-"),
        ("DHCP", dhcp),
    ]:
        info_labels[label] = add_info_row(left_col, label, value, label_width=22)

    iface_frame = tk.Frame(left_col, bg="white")
    iface_frame.pack(fill="x", padx=30, pady=8)
    tk.Label(iface_frame, text="Interface:", width=22, anchor="w",
             bg="white", fg="#444444", font=("Segoe UI", 10)).pack(side="left")

    info_labels["Interface"] = tk.Label(iface_frame, text=net["iface"], anchor="w", bg="white", fg="#000000",
             font=("Segoe UI", 10, "bold"), justify="left")
    info_labels["Interface"].pack(side="left", fill="x", expand=True)

    right_col = tk.Frame(net_content, bg="white")
    right_col.pack(side="right", fill="both", expand=True, padx=(20, 0))

    add_section_title(right_col, "Netzwerkeinstellungen ändern", top_padding=0)
    for hint_line in [
        "Hinweis: Für fixe IP sind IP, Subnetz, Gateway und DNS1 Pflicht. Subnetz als 255.255.255.0 oder 24.",
        "Die Eingabefelder bleiben bei Umschaltungen unverändert.",
        "„Einstellungen zurücksetzen“ stellt die ursprüngliche Konfiguration wieder her, die beim Start des Programms geladen wurde.",
    ]:
        tk.Label(
            right_col,
            text=hint_line,
            font=("Segoe UI", 9),
            fg="#666666",
            bg="white",
            justify="left",
            anchor="w",
            wraplength=820,
        ).pack(anchor="w", padx=30, pady=(0, 2))
    tk.Frame(right_col, bg="white", height=6).pack()

    entries = {}

    ext_list = net.get("extended_list", [])
    ext_ips = [ip for ip, _ in ext_list]
    ext_subnets = [prefix_to_mask(prefix) for _, prefix in ext_list]

    def make_ip_row(label, keys, widths):
        frame = tk.Frame(right_col, bg="white")
        frame.pack(fill="x", padx=30, pady=7)
        tk.Label(frame, text=label + ":", width=12, anchor="w",
                 bg="white", fg="#444444").pack(side="left")
        for key, w in zip(keys, widths):
            e = tk.Entry(frame, width=w, font=("Segoe UI", 10), bg="white", relief="solid", bd=1)
            e.pack(side="left", padx=4)
            entries[key] = e

    def open_iface_properties(name):
        if name in ("Keine Verbindung", ""):
            os.startfile("ncpa.cpl")
            return
        ps = (
            'Add-Type -AssemblyName System.Windows.Forms\n'
            '$s = New-Object -ComObject Shell.Application\n'
            '$n = $s.NameSpace("shell:::{7007ACC7-3202-11D1-AAD2-00805FC1270E}")\n'
            '$i = $n.Items() | Where-Object { $_.Name -eq "' + name + '" }\n'
            'if ($i) {\n'
            '    $i.InvokeVerb("properties")\n'
                '    Start-Sleep -Milliseconds 1500\n'
            '    [System.Windows.Forms.SendKeys]::SendWait("i")\n'
            '    Start-Sleep -Milliseconds 300\n'
            '    [System.Windows.Forms.SendKeys]::SendWait("{TAB}")\n'
            '    Start-Sleep -Milliseconds 200\n'
            '    [System.Windows.Forms.SendKeys]::SendWait("{TAB}")\n'
            '    Start-Sleep -Milliseconds 200\n'
            '    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")\n'
            '}\n'
            'while ($true) {\n'
            '    [System.Windows.Forms.Application]::DoEvents()\n'
            '    Start-Sleep -Milliseconds 100\n'
            '}\n'
        )
        ps_path = os.path.join(os.environ.get("TEMP", "."), "kdtool_open_props.ps1")
        try:
            with open(ps_path, "w") as f:
                f.write(ps)
            subprocess.Popen(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden",
                 "-ExecutionPolicy", "Bypass", "-File", ps_path]
            )
        except Exception:
            os.startfile("ncpa.cpl")

    ip_frame = tk.Frame(right_col, bg="white")
    ip_frame.pack(fill="x", padx=30, pady=7)
    tk.Label(ip_frame, text="IP:", width=12, anchor="w",
             bg="white", fg="#444444").pack(side="left")
    for key, w in zip(["IP", "IP_EXT1", "IP_EXT2"], [15, 15, 15]):
        e = tk.Entry(ip_frame, width=w, font=("Segoe UI", 10), bg="white", relief="solid", bd=1)
        e.pack(side="left", padx=4)
        entries[key] = e
    tk.Button(ip_frame, text="Netzwerkeinstellungen öffnen", font=("Segoe UI", 8),
              bg="#0078d4", fg="white", relief="flat", cursor="hand2",
              command=lambda: open_iface_properties(net["iface"])).pack(side="left", padx=(10, 0))

    make_ip_row("Subnetz", ["Subnetz", "Subnetz_EXT1", "Subnetz_EXT2"], [15, 15, 15])
    make_ip_row("Gateway", ["Gateway"], [15])
    make_ip_row("DNS1", ["DNS1"], [15])
    make_ip_row("DNS2", ["DNS2"], [15])

    if net["ip"] == "Keine Verbindung":
        entry_values = {"ip": "", "subnet": "", "gateway": "", "dns1": "", "dns2": ""}
        ext_ip_vals = ["", ""]
        ext_sub_vals = ["", ""]
    else:
        entry_values = net
        ext_ip_vals = [ext_ips[i] if i < len(ext_ips) else "" for i in range(2)]
        ext_sub_vals = [ext_subnets[i] if i < len(ext_subnets) else "" for i in range(2)]

    entries["IP"].insert(0, entry_values["ip"])
    entries["Subnetz"].insert(0, entry_values["subnet"])
    entries["Gateway"].insert(0, entry_values["gateway"])
    entries["DNS1"].insert(0, entry_values["dns1"])
    entries["DNS2"].insert(0, entry_values["dns2"])
    entries["IP_EXT1"].insert(0, ext_ip_vals[0])
    entries["IP_EXT2"].insert(0, ext_ip_vals[1])
    entries["Subnetz_EXT1"].insert(0, ext_sub_vals[0])
    entries["Subnetz_EXT2"].insert(0, ext_sub_vals[1])

    try:
        save_network_backup(entries, dhcp == "Ja")
    except OSError:
        pass

    btn_frame = tk.Frame(right_col, bg="white")
    btn_frame.pack(anchor="w", padx=30, pady=10)

    status_frame = tk.Frame(right_col, bg="white", height=200)
    status_frame.pack(fill="x", padx=30, pady=(5, 12))
    status_frame.pack_propagate(False)

    status_label = tk.Label(
        status_frame,
        text="",
        bg="white",
        font=("Segoe UI", 11),
        fg="#333333",
        justify="left",
        anchor="nw",
        wraplength=900,
    )
    status_label.pack(fill="x")

    def show_status(message):
        if message.startswith("❌"):
            color = "#d32f2f"
        elif message.startswith("✅"):
            color = "#28a745"
        else:
            color = "#333333"
        status_label.config(text=message, fg=color)

    btn_state = "normal" if password_ok else "disabled"

    btn_dhcp = tk.Button(
        btn_frame,
        text="zu DHCP umschalten",
        bg="#d32f2f",
        fg="white",
        font=("Segoe UI", 11, "bold"),
        width=28,
        height=1,
        relief="flat",
        state=btn_state,
    )
    btn_dhcp.pack(side="left", padx=(0, 10))

    btn_static = tk.Button(
        btn_frame,
        text="Fixe IP setzen",
        bg="#0078d4",
        fg="white",
        font=("Segoe UI", 11, "bold"),
        width=28,
        height=1,
        relief="flat",
        state=btn_state,
    )
    btn_static.pack(side="left", padx=(0, 10))

    btn_restore = tk.Button(
        btn_frame,
        text="Einstellungen zurücksetzen",
        bg="#6c757d",
        fg="white",
        font=("Segoe UI", 11, "bold"),
        width=28,
        height=1,
        relief="flat",
        state=btn_state,
    )
    btn_restore.pack(side="left")

    status_label.pack(anchor="w", padx=30, pady=(5, 12))

    # ====================== FIREWALL ======================
    def _set_firewall_labels(fw_data):
        fw_private_label.config(text="")
        fw_public_label.config(text="")
        if fw_data:
            for name, enabled in fw_data.items():
                txt = "Ein" if enabled else "Aus"
                fg = "#28a745" if enabled else "#d32f2f"
                if name == "private":
                    fw_private_label.config(text=txt, fg=fg)
                elif name == "public":
                    fw_public_label.config(text=txt, fg=fg)
        else:
            fw_private_label.config(text="Fehler", fg="#999")
            fw_public_label.config(text="Fehler", fg="#999")

    def _refresh_firewall():
        _set_firewall_labels(get_firewall_status())

    def _toggle_firewall():
        if not is_admin():
            messagebox.showwarning(
                "Keine Administratorrechte",
                "Zum Ändern der Firewall-Einstellungen sind Administratorrechte erforderlich."
            )
            return
        try:
            ps = (
                '$allOn = $true; '
                'Get-NetFirewallProfile | ForEach-Object { if (!$_.Enabled) { $allOn = $false } }; '
                'if ($allOn) { '
                '  Get-NetFirewallProfile | Set-NetFirewallProfile -Enabled "False" '
                '} else { '
                '  Get-NetFirewallProfile | Set-NetFirewallProfile -Enabled "True" '
                '}; '
                'Start-Sleep -Seconds 2; '
                'Get-NetFirewallProfile | ForEach-Object { "$($_.Name):$($_.Enabled)" }'
            )
            out = run_powershell(ps).strip()
            fw_data = {}
            for line in out.splitlines():
                if ":" not in line: continue
                name, enabled = line.split(":", 1)
                fw_data[name.strip().lower()] = enabled.strip().lower() == "true"
            _set_firewall_labels(fw_data)
        except Exception:
            pass

    fw_state = "normal" if password_ok else "disabled"

    add_section_title(t1, "Firewall", top_padding=60)
    fw_row = tk.Frame(t1, bg="white")
    fw_row.pack(fill="x", padx=30, pady=5)
    tk.Label(fw_row, text="Privates Netzwerk:", width=20, anchor="w",
             bg="white", fg="#444444", font=("Segoe UI", 10)).pack(side="left")
    fw_private_label = tk.Label(fw_row, text="", anchor="w", bg="white",
                                font=("Segoe UI", 10, "bold"))
    fw_private_label.pack(side="left")

    fw_row2 = tk.Frame(t1, bg="white")
    fw_row2.pack(fill="x", padx=30, pady=5)
    tk.Label(fw_row2, text="Öffentliches Netzwerk:", width=20, anchor="w",
             bg="white", fg="#444444", font=("Segoe UI", 10)).pack(side="left")
    fw_public_label = tk.Label(fw_row2, text="", anchor="w", bg="white",
                               font=("Segoe UI", 10, "bold"))
    fw_public_label.pack(side="left")

    tk.Button(
        t1, text="Firewall ein-/ausschalten",
        bg="#d32f2f", fg="white",
        font=("Segoe UI", 11, "bold"),
        width=28, height=1,
        relief="flat",
        state=fw_state,
        command=_toggle_firewall,
    ).pack(anchor="w", padx=30, pady=(10, 5))

    _set_firewall_labels(firewall)

    t2 = ttk.Frame(tabs)

    def refresh_windows_data():
        new_windows = windows_info()
        new_update = get_last_windows_update()
        new_boot, new_uptime = get_uptime_str()
        win_pc_label.config(text=new_windows["PC Name"])
        win_sys_label.config(text=f"Windows {new_windows['Release']}")
        win_ver_label.config(text=new_windows["Version"])
        win_update_label.config(text=new_update)
        win_uptime_label.config(text=f"{new_boot} Uhr (Betriebszeit: {new_uptime})")
        for w in users_frame.winfo_children():
            w.destroy()
        try:
            users = run_powershell("Get-LocalUser | Select-Object -ExpandProperty Name").strip().splitlines()
            for u in users:
                u = u.strip()
                if u:
                    tk.Label(users_frame, text=f"  •  {u}", anchor="w", bg="white", fg="#333", font=("Segoe UI", 10)).pack(fill="x")
        except Exception:
            tk.Label(users_frame, text="  (Fehler beim Abrufen der Benutzer)", anchor="w", bg="white", fg="#999", font=("Segoe UI", 10)).pack(fill="x")

    add_section_title(t2, "Windows", top_padding=20, on_refresh=refresh_windows_data)
    win_pc_label = add_info_row(t2, "PC Name", windows["PC Name"], label_width=20)
    win_sys_label = add_info_row(t2, "System", f"Windows {windows['Release']}", label_width=20)
    win_ver_label = add_info_row(t2, "Version", windows["Version"], label_width=20)
    add_info_row(t2, "KDtool Version", version_str, label_width=20)
    win_update_label = add_info_row(t2, "Letztes Update am", last_windows_update, label_width=20)
    win_uptime_label = add_info_row(t2, "Letzter Neustart", f"{boot_time} Uhr (Betriebszeit: {uptime_str})", label_width=20)

    add_section_title(t2, "Benutzer", top_padding=20)
    users_frame = tk.Frame(t2, bg="white")
    users_frame.pack(fill="x", padx=30, pady=(0, 5))
    refresh_windows_data()

    def create_user01():
        ps = r"""
        $user = Get-LocalUser -Name "User01" -ErrorAction SilentlyContinue
        if (-not $user) {
            $pass = ConvertTo-SecureString "kasse" -AsPlainText -Force
            New-LocalUser -Name "User01" -Password $pass -PasswordNeverExpires | Out-Null
            Add-LocalGroupMember -Group (Get-LocalGroup -SID S-1-5-32-544) -Member "User01" 2>$null
            Write-Output "ERFOLG"
        } else {
            Write-Output "EXISTIERT"
        }
        """
        try:
            result = run_powershell(ps, bypass_policy=True).strip()
            if result == "ERFOLG":
                user_status_label.config(text="✅ Benutzer User01 wurde angelegt und den Administratoren hinzugefügt.", fg="#28a745")
                refresh_windows_data()
            else:
                user_status_label.config(text="ℹ️ Benutzer User01 existiert bereits.", fg="#d32f2f")
        except Exception:
            user_status_label.config(text="❌ Fehler beim Anlegen des Benutzers.", fg="#d32f2f")

    btn_user_frame = tk.Frame(t2, bg="white")
    btn_user_frame.pack(fill="x", padx=30, pady=(5, 10))
    tk.Button(
        btn_user_frame, text="Benutzer User01 anlegen", command=create_user01,
        bg="#0078d4", fg="white", font=("Segoe UI", 11, "bold"),
        width=28, height=1, relief="flat", state=btn_state,
    ).pack(anchor="w")

    user_status_label = tk.Label(
        t2, text="", bg="white", font=("Segoe UI", 11),
        fg="#333333", justify="left", anchor="w", wraplength=900,
    )
    user_status_label.pack(fill="x", padx=30, pady=(0, 10))

    t3 = ttk.Frame(tabs)

    def _open_printer_props(name):
        try:
            subprocess.Popen(
                ["rundll32.exe", "printui.dll,PrintUIEntry", "/p", "/n", name],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception:
            pass

    def _clear_printer_jobs(name):
        try:
            run_powershell(f'Get-PrintJob -PrinterName "{name}" | Remove-PrintJob')
        except Exception:
            pass
        root.after(200, _refresh_printers)

    def _print_test_page(name):
        try:
            subprocess.Popen(
                ["rundll32.exe", "printui.dll,PrintUIEntry", "/k", "/n", name],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception:
            pass

    def _refresh_printers():
        _printer_scan_complete[0] = False
        _update_tab_colors()
        for item in tree.get_children():
            tree.delete(item)
        for name, ip, job_count, err_flag in get_printers():
            err_txt = "Fehler" if err_flag == "1" else "OK"
            tree.insert("", "end", values=(name, ip, job_count, err_txt),
                        tags=("fehler",) if err_flag == "1" else ())
        _printer_scan_complete[0] = True
        _update_tab_colors()

    add_section_title(t3, "Drucker", top_padding=20, on_refresh=_refresh_printers)
    tree = ttk.Treeview(t3, columns=("Name", "IP", "Jobs", "Fehler"), show="headings")
    tree.heading("Name", text="Druckername")
    tree.heading("IP", text="IP / Port")
    tree.heading("Jobs", text="Druckaufträge")
    tree.heading("Fehler", text="Fehler")
    tree.column("Jobs", width=100, anchor="center")
    tree.column("Fehler", width=80, anchor="center")
    tree.tag_configure("fehler", background="#FFE0B2")
    tree.pack(fill="both", expand=True, padx=20, pady=10)
    for name, ip, job_count, err_flag in printers:
        err_txt = "Fehler" if err_flag == "1" else "OK"
        tree.insert("", "end", values=(name, ip, job_count, err_txt),
                    tags=("fehler",) if err_flag == "1" else ())
    _printer_scan_complete[0] = True

    tree.bind("<Double-1>", lambda e: _open_printer_props(
        tree.item(tree.selection()[0], "values")[0]
    ) if tree.selection() else None)

    ctx_menu = tk.Menu(t3, tearoff=0)
    ctx_menu.add_command(label="Alle Druckaufträge löschen",
                         command=lambda: _clear_printer_jobs(
                             tree.item(tree.selection()[0], "values")[0]
                         ) if tree.selection() else None)
    ctx_menu.add_command(label="Testseite drucken",
                         command=lambda: _print_test_page(
                             tree.item(tree.selection()[0], "values")[0]
                         ) if tree.selection() else None)
    def _show_ctx(e):
        item = tree.identify_row(e.y)
        if item:
            tree.selection_set(item)
            ctx_menu.tk_popup(e.x_root, e.y_root)
    tree.bind("<Button-3>", _show_ctx)

    spooler_bottom = tk.Frame(t3, bg="white")
    spooler_bottom.pack(fill="x", padx=20, pady=(5, 10))
    spooler_right = tk.Frame(spooler_bottom, bg="white")
    spooler_right.pack(side="right")
    tk.Button(
        spooler_right, text="Service Druckerwarteschlange neu starten",
        bg="#0078d4", fg="white",
        font=("Segoe UI", 11, "bold"),
        relief="flat", padx=16, pady=6,
        command=lambda: _restart_spooler(),
    ).pack(anchor="e")
    spooler_status = tk.Label(spooler_right, text="", font=("Segoe UI", 10), bg="white", anchor="e")
    spooler_status.pack(anchor="e", pady=(2, 0))

    def _restart_spooler():
        if not is_admin():
            spooler_status.config(text="❌ Adminrechte erforderlich", fg="#d32f2f")
            return
        spooler_status.config(text="⏳ Starte Druckerwarteschlange neu...", fg="#666666")
        try:
            run_powershell('Restart-Service -Name Spooler -Force')
            spooler_status.config(text="✅ Druckerwarteschlange neu gestartet", fg="#28a745")
        except Exception as e:
            spooler_status.config(text=f"❌ Neustart fehlgeschlagen: {e}", fg="#d32f2f")

    t4 = tk.Frame(tabs, bg="white")
    header = tk.Frame(t4, bg="white")
    header.pack(fill="x", padx=30, pady=(20, 5))
    tk.Label(header, text="Netzwerkgeräte", font=("Segoe UI", 13, "bold"), fg="#0078d4", bg="white"
             ).pack(side="left")
    tk.Button(header, text="↻ Aktualisieren", font=("Segoe UI", 9), bg="#0078d4", fg="white",
              relief="flat", padx=10, pady=2,
              command=lambda: _refresh_vlan_scan()
              ).pack(side="right")

    vlan_progress_frame = tk.Frame(t4, bg="white")
    vlan_progress_frame.pack(fill="x", padx=20, pady=(5, 10))

    vlan_progress_label = tk.Label(
        vlan_progress_frame, text="", font=("Segoe UI", 9), fg="#555555", bg="white", anchor="w"
    )
    vlan_progress_label.pack(fill="x")

    vlan_progress_bar = ttk.Progressbar(
        vlan_progress_frame,
        style="vlan.Horizontal.TProgressbar",
        mode="determinate",
        maximum=100,
    )
    vlan_progress_bar.pack(fill="x", pady=(3, 0))
    ttk.Style().configure("vlan.Horizontal.TProgressbar", background="#0078d4")

    vlan_content_frame = tk.Frame(t4, bg="white")
    vlan_content_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))

    vlan_left_frame = tk.Frame(vlan_content_frame, bg="white")
    vlan_left_frame.pack(side="left", fill="both", expand=True)

    vlan_primary_frame = tk.LabelFrame(vlan_left_frame, text="Hauptnetzwerk", bg="white", padx=5, pady=5)
    vlan_primary_frame.pack(fill="both", expand=True, pady=(0, 5))

    tree2_primary = ttk.Treeview(vlan_primary_frame, columns=("IP", "Name", "MAC"), show="headings", height=8)
    tree2_primary.heading("IP", text="IP-Adresse")
    tree2_primary.heading("Name", text="Name / Hersteller")
    tree2_primary.heading("MAC", text="MAC-Adresse")
    tree2_primary.column("IP", width=160, anchor="w")
    tree2_primary.column("Name", width=320, anchor="w")
    tree2_primary.column("MAC", width=180, anchor="w")
    tree2_primary.pack(fill="both", expand=True, padx=5, pady=5)

    vlan_extended_frame = tk.LabelFrame(vlan_left_frame, text="Erweiterte Netzwerke", bg="white", padx=5, pady=5)

    tree2_extended = ttk.Treeview(vlan_extended_frame, columns=("IP", "Name", "MAC"), show="headings", height=5)
    tree2_extended.heading("IP", text="IP-Adresse")
    tree2_extended.heading("Name", text="Name / Hersteller")
    tree2_extended.heading("MAC", text="MAC-Adresse")
    tree2_extended.column("IP", width=160, anchor="w")
    tree2_extended.column("Name", width=320, anchor="w")
    tree2_extended.column("MAC", width=180, anchor="w")
    tree2_extended.pack(fill="both", expand=True, padx=5, pady=5)

    if net.get("extended_list"):
        vlan_extended_frame.pack(fill="both", expand=True, pady=(5, 0))
    else:
        vlan_extended_frame.pack_forget()

    vlan_ping_frame = tk.Frame(vlan_content_frame, bg="white")
    ping_process = [None]

    def _copy_mac(mac):
        root.clipboard_clear()
        root.clipboard_append(mac)
        messagebox.showinfo("Zwischenablage", f"MAC-Adresse {mac} wurde kopiert.")

    def _lookup_mac(mac):
        root.clipboard_clear()
        root.clipboard_append(mac)
        webbrowser.open("https://www.macvendorlookup.com/")
        ps = f'''
Add-Type -AssemblyName System.Windows.Forms
Start-Sleep -Seconds 2.5
[System.Windows.Forms.SendKeys]::SendWait('^v')
'''
        subprocess.Popen(["powershell", "-NoProfile", "-Command", ps],
                         creationflags=subprocess.CREATE_NO_WINDOW)

    def show_row_menu(event):
        tree = event.widget
        item = tree.identify_row(event.y)
        if not item:
            return
        values = tree.item(item, "values")
        if not values or len(values) < 3:
            return
        ip = values[0]
        mac = values[2].strip()
        menu = tk.Menu(root, tearoff=0)
        if is_ipv4_address(ip):
            menu.add_command(label=f"Ping ({ip})", command=lambda ip=ip: _show_ping(ip))
        if mac and re.match(r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$", mac):
            menu.add_command(label=f"MAC-Adresse kopieren ({mac})",
                             command=lambda m=mac: _copy_mac(m))
            menu.add_command(label=f"MAC-Adresse suchen ({mac})",
                             command=lambda m=mac: _lookup_mac(m))
        if menu.index("end") is not None:
            menu.tk_popup(event.x_root, event.y_root)

    def _show_ping(ip):
        if ping_process[0]:
            ping_process[0].kill()
            ping_process[0] = None
        for w in vlan_ping_frame.winfo_children():
            w.destroy()
        vlan_ping_frame.pack(side="left", fill="both", expand=True, padx=(10, 0))

        tk.Label(vlan_ping_frame, text=f"Ping: {ip}", font=("Segoe UI", 11, "bold"),
                 bg="white", fg="#333333").pack(anchor="w", pady=(0, 5))

        ping_text = tk.Text(vlan_ping_frame, font=("Consolas", 10), bg="#f5f5f5", fg="#222222",
                            relief="solid", bd=1, wrap="none", state="disabled")
        ping_text.pack(fill="both", expand=True)

        def close_ping():
            if ping_process[0]:
                try:
                    ping_process[0].kill()
                except Exception:
                    pass
                ping_process[0] = None
            vlan_ping_frame.pack_forget()

        tk.Button(vlan_ping_frame, text="Ping schliessen", font=("Segoe UI", 10),
                  bg="#d32f2f", fg="white", relief="flat", padx=12, pady=4,
                  command=close_ping).pack(anchor="w", pady=(8, 0))

        def run_ping():
            try:
                proc = subprocess.Popen(
                    ["ping", "-t", ip],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding=_oem_encoding(), errors="replace", creationflags=subprocess.CREATE_NO_WINDOW
                )
                ping_process[0] = proc
                for line in proc.stdout:
                    if not line:
                        break
                    ping_text.after(0, lambda l=line: _append_ping(l))
                proc.wait()
            except Exception as e:
                ping_text.after(0, lambda: _append_ping(f"Fehler: {e}\n"))
            finally:
                if ping_process[0] == proc:
                    ping_process[0] = None

        def _append_ping(text):
            try:
                ping_text.config(state="normal")
                ping_text.insert("end", text)
                ping_text.see("end")
                ping_text.config(state="disabled")
            except tk.TclError:
                pass

        threading.Thread(target=run_ping, daemon=True).start()

    def open_vlan_ip_in_browser(event):
        tree = event.widget
        item = tree.identify_row(event.y)
        if not item:
            return
        values = tree.item(item, "values")
        if not values:
            return
        ip = values[0]
        if is_ipv4_address(ip):
            webbrowser.open(f"http://{ip}")

    tree2_primary.bind("<Double-1>", open_vlan_ip_in_browser)
    tree2_extended.bind("<Double-1>", open_vlan_ip_in_browser)
    tree2_primary.bind("<Button-3>", show_row_menu)
    tree2_extended.bind("<Button-3>", show_row_menu)

    def set_report_buttons_state(enabled):
        state = "normal" if enabled else "disabled"
        try:
            btn_email.config(state=state)
            btn_text.config(state=state)
        except:
            pass

    def on_scan_done():
        _vlan_scan_complete[0] = True
        _update_tab_colors()
        set_report_buttons_state(True)
        try:
            if "OK" not in internet_label.cget("text"):
                btn_email.config(state="disabled")
        except:
            pass

    def _refresh_vlan_scan():
        _vlan_scan_complete[0] = False
        _update_tab_colors()
        set_report_buttons_state(False)
        global vlan_scan_id
        vlan_scan_id += 1
        for item in tree2_primary.get_children():
            tree2_primary.delete(item)
        for item in tree2_extended.get_children():
            tree2_extended.delete(item)
        vlan_progress_bar.config(value=0)
        vlan_progress_label.config(text="Starte Scan …")
        if _cur_net.get("extended_list"):
            vlan_extended_frame.pack(fill="both", expand=True, pady=(5, 0))
        else:
            vlan_extended_frame.pack_forget()
        load_vlan(
            tree2_primary, tree2_extended, root, _cur_net["ip"], _cur_net.get("extended_list", []),
            progress_label=vlan_progress_label, progress_bar=vlan_progress_bar,
            on_scan_done=on_scan_done,
        )

    load_vlan(
        tree2_primary, tree2_extended, root, _cur_net["ip"], _cur_net.get("extended_list", []),
        progress_label=vlan_progress_label, progress_bar=vlan_progress_bar,
        on_scan_done=on_scan_done,
    )

    ip_renew_bottom = tk.Frame(t4, bg="white")
    ip_renew_bottom.pack(fill="x", padx=20, pady=(5, 10))
    ip_renew_right = tk.Frame(ip_renew_bottom, bg="white")
    ip_renew_right.pack(side="right")

    def _renew_ip():
        def worker():
            ip_renew_status.config(text="⏳ IP-Adresse wird erneuert ...", fg="#666666")
            try:
                subprocess.run(["ipconfig", "/release"], capture_output=True, **_subprocess_kwargs())
                subprocess.run(["ipconfig", "/renew"], capture_output=True, **_subprocess_kwargs())
                ip_renew_status.config(text="✅ IP-Adresse erneuert", fg="#28a745")
                _refresh_vlan_scan()
            except Exception as e:
                ip_renew_status.config(text=f"❌ Fehler: {e}", fg="#d32f2f")
        threading.Thread(target=worker, daemon=True).start()

    tk.Button(
        ip_renew_right, text="IP Adresse erneuern",
        bg="#0078d4", fg="white",
        font=("Segoe UI", 11, "bold"),
        relief="flat", padx=16, pady=6,
        command=_renew_ip,
    ).pack(anchor="e")
    ip_renew_status = tk.Label(ip_renew_right, text="", font=("Segoe UI", 10), bg="white", anchor="e")
    ip_renew_status.pack(anchor="e", pady=(2, 0))

    def run_network_change(action):
        message = action()
        show_status(message)
        if message.startswith("✅"):
            info_labels["DHCP"].config(text="Ja" if action is set_dhcp else "Nein")
            refresh_network_display()

    def restore_network_settings():
        backup = load_network_backup()
        if not backup:
            show_status("❌ Keine gesicherten Einstellungen gefunden.")
            return

        fill_entries_from_snapshot(entries, backup)

        if backup.get("dhcp") == "Ja":
            message = set_dhcp()
        else:
            message = set_static_ip(
                backup.get("ip", ""),
                backup.get("subnet", ""),
                backup.get("gateway", ""),
                backup.get("dns1", ""),
                backup.get("dns2", ""),
                extended_ips=[(backup.get("ip_ext1", ""), backup.get("sub_ext1", "")),
                               (backup.get("ip_ext2", ""), backup.get("sub_ext2", ""))],
            )
            if message.startswith("✅"):
                msg = "✅ Einstellungen zurückgesetzt"
                msg += f"\nIP: {backup.get('ip', '')}"
                msg += f"\nSubnetz: {backup.get('subnet', '')}"
                msg += f"\nGateway: {backup.get('gateway', '')}"
                msg += f"\nDNS: {backup.get('dns1', '')}"
                for i in (1, 2):
                    eip = backup.get(f"ip_ext{i}", "")
                    if eip:
                        esub = backup.get(f"sub_ext{i}", "")
                        msg += f"\nErw. IP {i}: {eip} {esub}"
                message = msg

        show_status(message)
        if message.startswith("✅"):
            info_labels["DHCP"].config(text=backup.get("dhcp", "Nein"))
            refresh_network_display()

    btn_dhcp.config(command=lambda: run_network_change(set_dhcp))
    btn_static.config(
        command=lambda: run_network_change(
            lambda: set_static_ip(
                entries["IP"].get().strip(),
                entries["Subnetz"].get().strip(),
                entries["Gateway"].get().strip(),
                entries["DNS1"].get().strip(),
                entries["DNS2"].get().strip(),
                extended_ips=[(entries["IP_EXT1"].get().strip(), entries["Subnetz_EXT1"].get().strip()),
                               (entries["IP_EXT2"].get().strip(), entries["Subnetz_EXT2"].get().strip())],
            )
        )
    )
    btn_restore.config(command=restore_network_settings)

    t5 = ttk.Frame(tabs)

    def _refresh_kasse():
        nonlocal _cur_kasse_ordner, _cur_kasse_firma_data
        new_ver = get_kasse_version()
        new_install = get_kasse_install_datum()
        new_ordner, new_ws = get_kasse_data()
        vers_label.config(text=new_ver)
        install_label.config(text=new_install)
        ordner_label.config(text=new_ordner if new_ordner else "Nicht gefunden")
        ws_label.config(text=new_ws)
        _cur_kasse_ordner = new_ordner
        _cur_kasse_ws[0] = new_ws
        new_firma, _ = extract_firma_data(new_ordner)
        _cur_kasse_firma_data = new_firma
        if new_firma:
            firma_labels["firma_name"].config(text=new_firma.get("fabetrieb", ""), fg="#000000")
            firma_labels["firma_strasse"].config(text=new_firma.get("fafirmaadresse", ""), fg="#000000")
            plz = new_firma.get("fafirmaplz", "")
            ort = new_firma.get("faort", "")
            firma_labels["firma_plzort"].config(text=f"{plz} {ort}".strip(), fg="#000000")
            bs_labels["bs_name"].config(text=new_firma.get("falocationname", ""), fg="#000000")
            bs_labels["bs_adresse"].config(text=new_firma.get("falocationadresse", ""), fg="#000000")
            bs_plz = new_firma.get("falocationplz", "")
            bs_ort = new_firma.get("falocationort", "")
            bs_labels["bs_plzort"].config(text=f"{bs_plz} {bs_ort}".strip(), fg="#000000")
        else:
            for lbl in firma_labels.values():
                lbl.config(text="Nicht verfügbar", fg="#d32f2f")
            for lbl in bs_labels.values():
                lbl.config(text="Nicht verfügbar", fg="#d32f2f")
        _update_tab_colors()

    add_section_title(t5, "Kasse", top_padding=20, on_refresh=_refresh_kasse)
    vers_label = add_info_row(t5, "Version", kasse_version)
    install_label = add_info_row(t5, "Installiert am", kasse_install_datum)
    ordner_label = add_kasse_ordner_row(t5, kasse_ordner)
    ws_label = add_info_row(t5, "Arbeitsstationen", arbeitsstationen)

    kasse_data_sep = tk.Frame(t5, bg="#e0e0e0", height=1)
    kasse_data_sep.pack(fill="x", padx=30, pady=15)

    tk.Label(t5, text="Firma", font=("Segoe UI", 11, "bold"),
             fg="#0078d4", bg="white").pack(anchor="w", padx=30, pady=(0, 2))

    firma_labels = {}
    for k, lbl in [("firma_name", "Name"), ("firma_strasse", "Strasse"), ("firma_plzort", "PLZ/Ort")]:
        row = tk.Frame(t5, bg="white")
        row.pack(fill="x", padx=30, pady=2)
        tk.Label(row, text=f"{lbl}:", width=12, anchor="w", bg="white", fg="#444444",
                 font=("Segoe UI", 10)).pack(side="left")
        txt = ""
        if k == "firma_name" and kasse_firma_data:
            txt = kasse_firma_data.get("fabetrieb", "")
        elif k == "firma_strasse" and kasse_firma_data:
            txt = kasse_firma_data.get("fafirmaadresse", "")
        elif k == "firma_plzort" and kasse_firma_data:
            plz = kasse_firma_data.get("fafirmaplz", "")
            ort = kasse_firma_data.get("faort", "")
            txt = f"{plz} {ort}".strip()
        val = tk.Label(row, text=txt or "Nicht verfügbar", anchor="w", bg="white",
                       fg="#000000" if txt else "#d32f2f",
                       font=("Segoe UI", 10, "bold"))
        val.pack(side="left")
        firma_labels[k] = val

    tk.Label(t5, text="Betriebsstätte", font=("Segoe UI", 11, "bold"),
             fg="#0078d4", bg="white").pack(anchor="w", padx=30, pady=(12, 2))

    bs_labels = {}
    for k, lbl in [("bs_name", "Name"), ("bs_adresse", "Adresse"), ("bs_plzort", "PLZ/Ort")]:
        row = tk.Frame(t5, bg="white")
        row.pack(fill="x", padx=30, pady=2)
        tk.Label(row, text=f"{lbl}:", width=12, anchor="w", bg="white", fg="#444444",
                 font=("Segoe UI", 10)).pack(side="left")
        txt = ""
        if k == "bs_name" and kasse_firma_data:
            txt = kasse_firma_data.get("falocationname", "")
        elif k == "bs_adresse" and kasse_firma_data:
            txt = kasse_firma_data.get("falocationadresse", "")
        elif k == "bs_plzort" and kasse_firma_data:
            plz = kasse_firma_data.get("falocationplz", "")
            ort = kasse_firma_data.get("falocationort", "")
            txt = f"{plz} {ort}".strip()
        val = tk.Label(row, text=txt or "Nicht verfügbar", anchor="w", bg="white",
                       fg="#000000" if txt else "#d32f2f",
                       font=("Segoe UI", 10, "bold"))
        val.pack(side="left")
        bs_labels[k] = val

    kasse_bottom = tk.Frame(t5, bg="white")
    kasse_bottom.pack(side="bottom", fill="x", padx=30, pady=(15, 10))
    kasse_right = tk.Frame(kasse_bottom, bg="white")
    kasse_right.pack(side="right")
    tk.Button(
        kasse_right, text="Kasse starten (001)",
        bg="#0078d4", fg="white",
        font=("Segoe UI", 11, "bold"),
        relief="flat", padx=16, pady=6,
        command=lambda: _start_kasse(),
    ).pack(anchor="e")
    kasse_status = tk.Label(kasse_right, text="", font=("Segoe UI", 10), bg="white", anchor="e")
    kasse_status.pack(anchor="e", pady=(2, 0))

    def _start_kasse():
        folder = _cur_kasse_ordner
        if not folder:
            kasse_status.config(text="❌ Kein Kassenordner gefunden", fg="#d32f2f")
            return
        exe1 = os.path.join(folder, "x3000.exe")
        exe2 = os.path.join(folder, "kassa.exe")
        exe = exe1 if os.path.isfile(exe1) else (exe2 if os.path.isfile(exe2) else None)
        if not exe:
            kasse_status.config(
                text=f"❌ Keine Exe gefunden in: {folder}",
                fg="#d32f2f"
            )
            return
        try:
            subprocess.Popen(f'"{exe}" 001', cwd=folder, shell=True)
            kasse_status.config(text=f"✅ Kasse gestartet ({exe})", fg="#28a745")
        except Exception as e:
            kasse_status.config(text=f"❌ Fehler: {e}", fg="#d32f2f")

    t6 = ttk.Frame(tabs)
    def _refresh_internet():
        new_status = internet_status()
        internet_label.config(
            text=new_status,
            fg="#28a745" if "OK" in new_status else "#d32f2f",
        )
        try:
            if "OK" in new_status:
                btn_email.config(state="normal")
            else:
                btn_email.config(state="disabled")
        except:
            pass
        _update_tab_colors()
    add_section_title(t6, "Internet", top_padding=20, on_refresh=_refresh_internet)
    internet_label = add_info_row(
        t6, "Status", internet,
        value_fg="#28a745" if "OK" in internet else "#d32f2f",
    )

    t7 = ttk.Frame(tabs)

    def _refresh_fernwartung():
        nonlocal _cur_tv_id, _cur_anydesk_id
        tv_exe = find_teamviewer_exe()
        tv_inst = tv_exe is not None
        tv_installed_label.config(text="Ja" if tv_inst else "Nein",
                                  fg="#28a745" if tv_inst else "#d32f2f")
        new_tv_id = get_teamviewer_id()
        tv_id_label.config(text=new_tv_id)
        _cur_tv_id = new_tv_id
        ad_exe = find_anydesk_exe()
        ad_inst = ad_exe is not None
        ad_installed_label.config(text="Ja" if ad_inst else "Nein",
                                  fg="#28a745" if ad_inst else "#d32f2f")
        new_ad_id = get_anydesk_id()
        ad_id_label.config(text=new_ad_id)
        _cur_anydesk_id = new_ad_id
        _update_tab_colors()

    add_section_title(t7, "TeamViewer", top_padding=20, on_refresh=_refresh_fernwartung)
    tv_installed_label = add_info_row(t7, "Installiert", "Ja" if find_teamviewer_exe() else "Nein", label_width=20,
                 value_fg="#28a745" if find_teamviewer_exe() else "#d32f2f")
    tv_id_label = add_info_row(t7, "TeamViewer ID", tv_id, label_width=20)

    tv_status_label = tk.Label(
        t7,
        text="",
        bg="white",
        font=("Segoe UI", 11),
        fg="#333333",
        justify="left",
        anchor="w",
        wraplength=820,
    )

    def on_open_teamviewer():
        tv_status_label.config(text="TeamViewer wird gestartet …", fg="#333333")

        def worker():
            ok, message = open_teamviewer()
            color = "#28a745" if ok else "#d32f2f"
            root.after(0, lambda: tv_status_label.config(text=message, fg=color))

        threading.Thread(target=worker, daemon=True).start()

    tk.Button(
        t7,
        text="TeamViewer öffnen",
        bg="#0078d4",
        fg="white",
        font=("Segoe UI", 11, "bold"),
        width=22,
        height=1,
        relief="flat",
        command=on_open_teamviewer,
    ).pack(anchor="w", padx=30, pady=10)
    tv_status_label.pack(anchor="w", padx=30, pady=(0, 10))

    add_section_title(t7, "AnyDesk", top_padding=20)
    ad_installed_label = add_info_row(t7, "Installiert", "Ja" if find_anydesk_exe() else "Nein", label_width=20,
                 value_fg="#28a745" if find_anydesk_exe() else "#d32f2f")
    ad_id_label = add_info_row(t7, "AnyDesk ID", anydesk_id, label_width=20)

    ad_status_label = tk.Label(
        t7,
        text="",
        bg="white",
        font=("Segoe UI", 11),
        fg="#333333",
        justify="left",
        anchor="w",
        wraplength=820,
    )

    def on_open_anydesk():
        ad_status_label.config(text="AnyDesk wird gestartet …", fg="#333333")

        def worker():
            ok, message = open_anydesk()
            color = "#28a745" if ok else "#d32f2f"
            root.after(0, lambda: ad_status_label.config(text=message, fg=color))

        threading.Thread(target=worker, daemon=True).start()

    tk.Button(
        t7,
        text="AnyDesk öffnen",
        bg="#0078d4",
        fg="white",
        font=("Segoe UI", 11, "bold"),
        width=22,
        height=1,
        relief="flat",
        command=on_open_anydesk,
    ).pack(anchor="w", padx=30, pady=10)
    ad_status_label.pack(anchor="w", padx=30, pady=(0, 10))

    if password_ok:
        t_cleanup = tk.Frame(tabs, bg="white")

        drives_frame = tk.LabelFrame(t_cleanup, text="Lokale Laufwerke", bg="white", padx=5, pady=5)

        ttk.Style().configure("drive.blue.Horizontal.TProgressbar", background="#0078d4")
        ttk.Style().configure("drive.orange.Horizontal.TProgressbar", background="#f57c00")
        ttk.Style().configure("drive.red.Horizontal.TProgressbar", background="#d32f2f")

        def add_drive_row(parent, letter, total, used, pct):
            row = tk.Frame(parent, bg="white")
            row.pack(fill="x", padx=10, pady=4)
            tk.Label(row, text=f"{letter}:", width=4, anchor="w", bg="white",
                     fg="#444444", font=("Segoe UI", 10, "bold")).pack(side="left")
            if pct >= 90:
                bar_style = "drive.red.Horizontal.TProgressbar"
            elif pct >= 70:
                bar_style = "drive.orange.Horizontal.TProgressbar"
            else:
                bar_style = "drive.blue.Horizontal.TProgressbar"
            ttk.Progressbar(row, style=bar_style, mode="determinate", maximum=100, value=pct).pack(
                side="left", padx=(0, 10), fill="x", expand=True)
            tk.Label(row, text=f"{used} GB von {total} GB belegt ({pct}%)", anchor="e",
                     bg="white", fg="#333333", font=("Segoe UI", 9), width=34).pack(side="left")

        def load_drives():
            ps = r"""
            Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Used -and $_.Free -and $_.Name -match '^[A-Z]$' } |
            ForEach-Object {
                $total = [math]::Round(($_.Used + $_.Free) / 1GB, 1)
                $used  = [math]::Round($_.Used / 1GB, 1)
                $pct   = [math]::Round(($_.Used / ($_.Used + $_.Free)) * 100, 0)
                "$($_.Name)|$total|$used|$pct"
            }
            """
            for w in drives_frame.winfo_children():
                w.destroy()
            try:
                out = run_powershell(ps).strip()
                if out:
                    for line in out.splitlines():
                        if "|" not in line: continue
                        parts = line.split("|")
                        if len(parts) >= 4:
                            add_drive_row(drives_frame, parts[0], parts[1], parts[2], int(parts[3]))
            except Exception:
                tk.Label(drives_frame, text="Fehler beim Abrufen der Laufwerksdaten",
                         fg="red", bg="white", font=("Segoe UI", 9)).pack()

        add_section_title(t_cleanup, "Datenträgerbereinigung", top_padding=20, on_refresh=load_drives)
        drives_frame.pack(fill="x", padx=20, pady=(5, 15))
        load_drives()

        middle_frame = tk.Frame(t_cleanup, bg="white")
        middle_frame.pack(fill="x", padx=20, pady=(0, 10))

        tasks_frame = tk.LabelFrame(middle_frame, text="Windows", bg="white", padx=5, pady=5)
        tasks_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

        task_vars = {}
        select_all_var = tk.BooleanVar()

        def on_select_all():
            val = select_all_var.get()
            for var in task_vars.values():
                var.set(val)

        tk.Checkbutton(tasks_frame, text="Alles auswählen", variable=select_all_var,
                        command=on_select_all, bg="white").pack(anchor="w", padx=10, pady=5)

        tasks = [
            ("cleanmgr",  "Datenträgerbereinigung (cleanmgr /lowdisk)"),
            ("dism",      "Alte Windows Updates bereinigen (DISM /StartComponentCleanup /ResetBase)"),
            ("hibernate", "Ruhezustand deaktivieren (powercfg -h off)"),
            ("temp_user", "Temporäre Dateien löschen (%TEMP%)"),
            ("temp_win",  "Windows Temp löschen (C:\\Windows\\Temp)"),
        ]

        for key, label in tasks:
            var = tk.BooleanVar()
            task_vars[key] = var
            tk.Checkbutton(tasks_frame, text=label, variable=var, bg="white").pack(anchor="w", padx=20, pady=2)

        kasse_frame = tk.LabelFrame(middle_frame, text="Kasse X3000", bg="white", padx=5, pady=5)
        kasse_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

        kasse_vars = {}
        kasse_select_all_var = tk.BooleanVar()

        def on_kasse_select_all():
            val = kasse_select_all_var.get()
            for var in kasse_vars.values():
                var.set(val)

        tk.Checkbutton(kasse_frame, text="Alles auswählen", variable=kasse_select_all_var,
                        command=on_kasse_select_all, bg="white").pack(anchor="w", padx=10, pady=5)

        kasse_tasks = [
            ("kasse_1", "Punkt 1"),
            ("kasse_2", "Punkt 2"),
            ("kasse_3", "Punkt 3"),
            ("kasse_4", "Punkt 4"),
            ("kasse_5", "Punkt 5"),
        ]

        for key, label in kasse_tasks:
            var = tk.BooleanVar()
            kasse_vars[key] = var
            tk.Checkbutton(kasse_frame, text=label, variable=var, bg="white").pack(anchor="w", padx=20, pady=2)

        adobe_frame = tk.LabelFrame(middle_frame, text="Sonstiges", bg="white", padx=5, pady=5)
        adobe_frame.pack(side="left", fill="y")

        adobe_var = tk.BooleanVar()
        tk.Checkbutton(adobe_frame, text="Adobe Reader / Acrobat deinstallieren", variable=adobe_var, bg="white").pack(
            anchor="w", padx=10, pady=5)
        bm_var = tk.BooleanVar()
        tk.Checkbutton(adobe_frame, text="Backup Maker deinstallieren", variable=bm_var, bg="white").pack(
            anchor="w", padx=10, pady=2)

        output_text = tk.Text(t_cleanup, height=10, font=("Consolas", 9), bg="white", fg="#222222",
                              relief="solid", bd=1, wrap="word")
        output_text.pack(fill="both", expand=True, padx=20, pady=(0, 5))

        task_status_label = tk.Label(t_cleanup, text="", font=("Segoe UI", 10), fg="#0078d4", bg="white", anchor="w")
        task_status_label.pack(fill="x", padx=20, pady=(0, 5))

        def append_output(msg):
            output_text.insert("end", msg + "\n")
            output_text.see("end")

        def run_cleanup():
            if not is_admin():
                cleanup_status.config(text="❌ Administrator-Rechte erforderlich", fg="#d32f2f")
                return

            selected = [k for k, v in task_vars.items() if v.get()]
            kasse_selected = [k for k, v in kasse_vars.items() if v.get()]
            if not selected and not kasse_selected and not adobe_var.get() and not bm_var.get():
                cleanup_status.config(text="⚠ Keine Aufgaben ausgewählt", fg="#ff8c00")
                return

            cleanup_status.config(text="✅ Bereinigung gestartet", fg="#28a745")
            output_text.delete("1.0", "end")
            append_output("Starte Bereinigung ...\n")

            def worker():
                def log(msg):
                    root.after(0, lambda: append_output(msg))

                def status(msg):
                    root.after(0, lambda: task_status_label.config(text=msg))

                if "cleanmgr" in selected:
                    log(">>> Datenträgerbereinigung wird gestartet ...")
                    status("cleanmgr /lowdisk läuft ...")
                    subprocess.run(["cleanmgr", "/lowdisk"], capture_output=True, **_subprocess_kwargs())

                if "dism" in selected:
                    log(">>> DISM bereinigt alte Updates (dieser Vorgang kann mehrere Minuten dauern) ...")
                    status("DISM läuft – bitte warten ...")
                    run_powershell("DISM /Online /Cleanup-Image /StartComponentCleanup /ResetBase")
                    status("")

                if "hibernate" in selected:
                    log(">>> Ruhezustand deaktivieren ...")
                    run_powershell("powercfg -h off")

                if "temp_user" in selected:
                    log(">>> Temporäre Dateien werden gelöscht ...")
                    status("Lösche %TEMP% ...")
                    subprocess.run(
                        ["cmd", "/c", f'rd /s /q "{os.environ["TEMP"]}" 2>nul & mkdir "{os.environ["TEMP"]}" 2>nul'],
                        **_subprocess_kwargs(),
                    )
                    log(">>> Temporäre Dateien gelöscht.")
                    status("")

                if "temp_win" in selected:
                    log(">>> Windows Temp wird gelöscht ...")
                    status("Lösche C:\\Windows\\Temp ...")
                    subprocess.run(
                        ["cmd", "/c", 'rd /s /q "C:\\Windows\\Temp" 2>nul & mkdir "C:\\Windows\\Temp" 2>nul'],
                        **_subprocess_kwargs(),
                    )
                    log(">>> Windows Temp gelöscht.")
                    status("")

                kasse_paths = {
                    "kasse_1": "C:\\Windows\\Temp",
                    "kasse_2": "C:\\Windows\\Temp",
                    "kasse_3": "C:\\Windows\\Temp",
                    "kasse_4": "C:\\Windows\\Temp",
                    "kasse_5": "C:\\Windows\\Temp",
                }
                for key in kasse_selected:
                    d = kasse_paths[key]
                    log(f">>> {d} wird gelöscht ...")
                    status(f"Lösche {d} ...")
                    subprocess.run(
                        ["cmd", "/c", f'rd /s /q "{d}" 2>nul & mkdir "{d}" 2>nul'],
                        **_subprocess_kwargs(),
                    )
                    log(f">>> {d} gelöscht.")
                    status("")

                if adobe_var.get():
                    log(">>> Deinstalliere Adobe Reader / Acrobat ...")
                    status("Deinstalliere Adobe Reader / Acrobat ...")
                    ps = r'''
                        $paths = @("HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
                                   "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*")
                        foreach ($path in $paths) {
                            Get-ItemProperty $path -ErrorAction SilentlyContinue | ForEach-Object {
                                $name = $_.DisplayName
                                if ($name -match "Adobe.*(Reader|Acrobat|AcroRead)") {
                                    $guid = $_.PSChildName
                                    if ($guid -match '^{\w{8}-\w{4}-\w{4}-\w{4}-\w{12}}$') {
                                        Write-Output $guid
                                    }
                                }
                            }
                        }
                    '''
                    adobe_guids = run_powershell(ps).strip().splitlines()
                    if not adobe_guids or (len(adobe_guids) == 1 and not adobe_guids[0]):
                        log("Keine Adobe-Reader/Acrobat-Installation gefunden.")
                    else:
                        for guid in adobe_guids:
                            guid = guid.strip()
                            if not guid: continue
                            log(f"Deinstalliere {guid} ...")
                            subprocess.Popen(
                                ["msiexec", "/X", guid, "/quiet", "/norestart"],
                                **_subprocess_kwargs()
                            )
                    log(">>> Adobe Reader / Acrobat Deinstallation abgeschlossen (sofern installiert).")
                    status("")

                if bm_var.get():
                    log(">>> Backup Maker wird deinstalliert …")
                    status("Suche Backup Maker …")
                    ps_bm = r'''
                        $paths = @("HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
                                   "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*")
                        $found = $false
                        foreach ($path in $paths) {
                            Get-ItemProperty $path -ErrorAction SilentlyContinue | ForEach-Object {
                                $name = $_.DisplayName
                                if ($name -match "[Bb]ackup.?[Mm]ak[ae]r") {
                                    $uninstall = $_.UninstallString
                                    if ($uninstall) {
                                        Write-Output $uninstall
                                        $found = $true
                                    }
                                }
                            }
                        }
                        if (-not $found) { Write-Output "NICHT_GEFUNDEN" }
                    '''
                    bm_out = run_powershell(ps_bm).strip()
                    if bm_out == "NICHT_GEFUNDEN":
                        log("   Backup Maker nicht gefunden.")
                    else:
                        for line in bm_out.splitlines():
                            line = line.strip()
                            if not line: continue
                            exe = line.strip('"')
                            status(f"Deinstalliere Backup Maker …")
                            log(f"   Starte {exe} …")
                            ps_cmd = (
                                f"taskkill /f /im BackupMaker.exe /im BackUpMaker.exe 2>$null; "
                                f"Start-Process '{exe}' -ArgumentList '/S'; "
                                "Start-Sleep 10; "
                                "Add-Type -AssemblyName System.Windows.Forms; "
                                "[System.Windows.Forms.SendKeys]::SendWait('{TAB}'); "
                                "Start-Sleep 0.3; "
                                "[System.Windows.Forms.SendKeys]::SendWait('{ENTER}'); "
                                "Start-Sleep 10; "
                                "[System.Windows.Forms.SendKeys]::SendWait('{ENTER}')"
                            )
                            subprocess.run([
                                "powershell", "-NoProfile", "-WindowStyle", "Hidden", "-STA",
                                "-Command", ps_cmd
                            ])
                    log(">>> Backup Maker Deinstallation abgeschlossen.")
                    status("")

                status("")
                root.after(0, lambda: [append_output("\n✅ Bereinigung abgeschlossen!"),
                                       cleanup_status.config(text="✅ Bereinigung abgeschlossen", fg="#28a745")])

            threading.Thread(target=worker, daemon=True).start()

        tk.Button(
            t_cleanup,
            text="Bereinigen",
            bg="#0078d4",
            fg="white",
            font=("Segoe UI", 11, "bold"),
            relief="flat", padx=16, pady=6,
            command=run_cleanup,
        ).pack(anchor="e", padx=20, pady=(5, 2))
        cleanup_status = tk.Label(t_cleanup, text="", font=("Segoe UI", 10), bg="white", anchor="e")
        cleanup_status.pack(anchor="e", padx=20, pady=(0, 10))

    # ====================== ZUSATZFUNKTIONEN ======================
    t_zusatz = tk.Frame(tabs, bg="white")

    add_section_title(t_zusatz, "Zweitkasse vorbereiten", top_padding=20)

    row = tk.Frame(t_zusatz, bg="white")
    row.pack(fill="x", padx=30, pady=10)
    tk.Label(row, text="Hauptkasse:", width=16, anchor="w", bg="white", fg="#444444",
             font=("Segoe UI", 10)).pack(side="left")
    server_entry = tk.Entry(row, width=40, font=("Segoe UI", 10), bg="white", relief="solid", bd=1)
    server_entry.pack(side="left", padx=8)
    server_entry.insert(0, "\\\\MAGELLAN-KASSE1\\")
    tk.Label(row, text="\\\\MAGELLAN-KASSE1\\", anchor="w", bg="white", fg="#888888",
             font=("Segoe UI", 10, "italic")).pack(side="left", padx=4)

    info_frame = tk.Frame(t_zusatz, bg="white")
    info_frame.pack(fill="x", padx=30, pady=5)
    for text in [
        "➤ Ändert die Server-Adresse in der param.ini gemäss Textfeld",
        "➤ Löscht das Install-Verzeichnis (C:\\X3000\\Install)",
        "➤ Löscht das Backup-Verzeichnis (C:\\X3000\\X3000-backup)",
        "➤ Deinstalliert Adobe PDF Reader",
        "➤ Deinstalliert Backup Maker",
    ]:
        tk.Label(info_frame, text=text, anchor="w", bg="white", fg="#555555",
                 font=("Segoe UI", 10)).pack(anchor="w", pady=1)

    warn_label = tk.Label(t_zusatz, text="Willst du das wirklich? (Diese Aktion kann nicht rückgängig gemacht werden!)",
                           font=("Segoe UI", 10, "bold"), fg="#d32f2f", bg="white", anchor="w")
    warn_label.pack(fill="x", padx=30, pady=(15, 5))

    confirm_row = tk.Frame(t_zusatz, bg="white")
    confirm_row.pack(fill="x", padx=30, pady=(0, 10))
    tk.Label(confirm_row, text="Zum Bestätigen «ja» eingeben:", width=28, anchor="w", bg="white", fg="#444444",
             font=("Segoe UI", 10)).pack(side="left")
    confirm_entry = tk.Entry(confirm_row, width=15, font=("Segoe UI", 10), bg="white", relief="solid", bd=1)
    confirm_entry.pack(side="left", padx=8)

    zusatz_status = tk.Label(t_zusatz, text="", font=("Segoe UI", 10), fg="#333333", bg="white", anchor="w")

    def run_zusatz():
        confirm_entry.config(state="disabled")
        if confirm_entry.get().strip().lower() != "ja":
            zusatz_status.config(text="❌ Bitte «ja» eingeben um zu bestätigen.", fg="#d32f2f")
            confirm_entry.config(state="normal")
            return

        if not is_admin():
            zusatz_status.config(text="❌ Administrator-Rechte erforderlich.", fg="#d32f2f")
            confirm_entry.config(state="normal")
            return

        folder = _cur_kasse_ordner
        if not folder:
            zusatz_status.config(text="❌ Kassenordner nicht gefunden.", fg="#d32f2f")
            confirm_entry.config(state="normal")
            return

        server_raw = server_entry.get().strip().rstrip("\\")
        server_name = server_raw.lstrip("\\")
        if not server_name:
            zusatz_status.config(text="❌ Bitte einen gültigen Server angeben.", fg="#d32f2f")
            confirm_entry.config(state="normal")
            return

        zusatz_status.config(text="✅ Führe Aufgaben aus …", fg="#28a745")

        def worker():
            def log(msg):
                root.after(0, lambda: zusatz_status.config(text=msg, fg="#333333"))
            try:
                # 1. param.ini ändern
                ini_path = os.path.join(folder, "param.ini")
                if os.path.isfile(ini_path):
                    log(f"📝 Bearbeite {ini_path} …")
                    with open(ini_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    new_lines = []
                    for line in lines:
                        stripped = line.strip()
                        if stripped.startswith("SQLSERVER="):
                            old_srv = stripped.split("=", 1)[1]
                            new_lines.append(f"SQLSERVER={server_name}\n")
                            log(f"   SQLSERVER: {old_srv} → {server_name}")
                        elif stripped.startswith("SQLDATENBANK="):
                            parts = stripped.split("=", 1)
                            if len(parts) == 2:
                                db_val = parts[1]
                                new_val = db_val.replace("\\\\LAPTOP\\", f"\\\\{server_name}\\")
                                new_lines.append(f"SQLDATENBANK={new_val}\n")
                                log(f"   SQLDATENBANK: {db_val} → {new_val}")
                            else:
                                new_lines.append(line)
                        else:
                            new_lines.append(line)
                    with open(ini_path, "w", encoding="utf-8") as f:
                        f.writelines(new_lines)
                else:
                    log(f"⚠ {ini_path} nicht gefunden.")

                # 2. Install-Verzeichnis löschen
                parent = os.path.dirname(folder)
                install_dir = os.path.join(parent, "Install")
                log(f"🗑️ Lösche {install_dir} …")
                try:
                    if os.path.isdir(install_dir):
                        shutil.rmtree(install_dir, ignore_errors=True)
                        log(f"   ✓ Gelöscht." if not os.path.isdir(install_dir) else f"   ⚠ Konnte nicht vollständig gelöscht werden.")
                    else:
                        log(f"   ⚠ Nicht vorhanden.")
                except Exception as e:
                    log(f"   ❌ Fehler: {e}")

                # 3. Backup-Verzeichnis löschen
                for name in os.listdir(parent):
                    if "backup" in name.lower():
                        backup_dir = os.path.join(parent, name)
                        log(f"🗑️ Lösche {backup_dir} …")
                        try:
                            if os.path.isdir(backup_dir):
                                shutil.rmtree(backup_dir, ignore_errors=True)
                                log(f"   ✓ Gelöscht." if not os.path.isdir(backup_dir) else f"   ⚠ Konnte nicht vollständig gelöscht werden.")
                            else:
                                log(f"   ⚠ Nicht vorhanden.")
                        except Exception as e:
                            log(f"   ❌ Fehler: {e}")

                # 4. Adobe PDF Reader deinstallieren
                log("🔍 Suche Adobe Reader …")
                ps = r'''
                    $paths = @("HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
                               "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*")
                    foreach ($path in $paths) {
                        Get-ItemProperty $path -ErrorAction SilentlyContinue | ForEach-Object {
                            $name = $_.DisplayName
                            if ($name -match "Adobe.*(Reader|Acrobat|AcroRead)") {
                                $guid = $_.PSChildName
                                if ($guid -match '^{\w{8}-\w{4}-\w{4}-\w{4}-\w{12}}$') {
                                    Write-Output $guid
                                }
                            }
                        }
                    }
                '''
                adobe_guids = run_powershell(ps).strip().splitlines()
                for guid in adobe_guids:
                    guid = guid.strip()
                    if guid:
                        log(f"🗑️ Deinstalliere Adobe Reader ({guid}) …")
                        subprocess.Popen(
                            ["msiexec", "/X", guid, "/quiet", "/norestart"],
                            **_subprocess_kwargs()
                        )

                # 5. Backup Maker deinstallieren
                log("🔍 Suche Backup Maker …")
                ps_bm = r'''
                    $paths = @("HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
                               "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*")
                    $found = $false
                    foreach ($path in $paths) {
                        Get-ItemProperty $path -ErrorAction SilentlyContinue | ForEach-Object {
                            $name = $_.DisplayName
                            if ($name -match "[Bb]ackup.?[Mm]ak[ae]r") {
                                $guid = $_.PSChildName
                                $uninstall = $_.UninstallString
                                if ($guid -match '^{\w{8}-\w{4}-\w{4}-\w{4}-\w{12}}$') {
                                    Write-Output "GUID:$guid"
                                    $found = $true
                                } elseif ($uninstall) {
                                    Write-Output "EXE:$uninstall"
                                    $found = $true
                                }
                            }
                        }
                    }
                    if (-not $found) { Write-Output "NICHT_GEFUNDEN" }
                '''
                bm_out = run_powershell(ps_bm).strip()
                if bm_out == "NICHT_GEFUNDEN":
                    log("   ⚠ Backup Maker nicht gefunden.")
                else:
                    for line in bm_out.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith("GUID:"):
                            guid = line.split(":", 1)[1]
                            log(f"🗑️ Deinstalliere Backup Maker (MSI: {guid}) …")
                            subprocess.Popen(
                                ["msiexec", "/X", guid, "/quiet", "/norestart"],
                                **_subprocess_kwargs()
                            )
                        elif line.startswith("EXE:"):
                            exe = line.split(":", 1)[1].strip('"')
                            log(f"🗑️ Beende laufende Backup Maker Prozesse …")
                            log(f"🗑️ Deinstalliere Backup Maker ({exe}) …")
                            log("⏳ Warte auf Deinstallationsfenster …")
                            ps_cmd = (
                                f"taskkill /f /im BackupMaker.exe /im BackUpMaker.exe 2>$null; "
                                f"Start-Process '{exe}' -ArgumentList '/S'; "
                                "Start-Sleep 10; "
                                "Add-Type -AssemblyName System.Windows.Forms; "
                                "[System.Windows.Forms.SendKeys]::SendWait('{TAB}'); "
                                "Start-Sleep 0.3; "
                                "[System.Windows.Forms.SendKeys]::SendWait('{ENTER}'); "
                                "Start-Sleep 10; "
                                "[System.Windows.Forms.SendKeys]::SendWait('{ENTER}')"
                            )
                            subprocess.run([
                                "powershell", "-NoProfile", "-WindowStyle", "Hidden", "-STA",
                                "-Command", ps_cmd
                            ])

                root.after(0, lambda: zusatz_status.config(
                    text="✅ Aufgaben abgeschlossen! Bitte Programm neu starten.", fg="#28a745"))
            except Exception as exc:
                root.after(0, lambda: zusatz_status.config(
                    text=f"❌ Fehler: {exc}", fg="#d32f2f"))
            finally:
                root.after(0, lambda: confirm_entry.config(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    tk.Button(
        t_zusatz,
        text="Als zusätzliche Kasse vorbereiten",
        bg="#0078d4", fg="white",
        font=("Segoe UI", 11, "bold"),
        width=32, height=1,
        relief="flat",
        command=run_zusatz,
    ).pack(anchor="w", padx=30, pady=(5, 5))

    zusatz_status.pack(fill="x", padx=30, pady=(0, 5))

    # ====================== DATEN ÜBERMITTELN ======================
    t8 = tk.Frame(tabs, bg="white")
    scroll_canvas = tk.Canvas(t8, bg="white", highlightthickness=0)
    scrollbar = tk.Scrollbar(t8, orient="vertical", command=scroll_canvas.yview)
    scroll_frame = tk.Frame(scroll_canvas, bg="white")
    scroll_frame.bind("<Configure>", lambda e: scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all")))
    scroll_win = scroll_canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
    scroll_canvas.bind("<Configure>", lambda e: scroll_canvas.itemconfig(scroll_win, width=e.width))
    scroll_canvas.configure(yscrollcommand=scrollbar.set)
    scroll_canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    def _on_mousewheel(e):
        scroll_canvas.yview_scroll(int(-1*(e.delta/120)), "units")
    scroll_canvas.bind("<Enter>", lambda e: scroll_canvas.bind_all("<MouseWheel>", _on_mousewheel))
    scroll_canvas.bind("<Leave>", lambda e: scroll_canvas.unbind_all("<MouseWheel>"))

    def add_email_row(parent, label, show=None, width=60, default=""):
        row = tk.Frame(parent, bg="white")
        row.pack(fill="x", padx=30, pady=5)
        tk.Label(row, text=label, width=16, anchor="w", bg="white", fg="#444444",
                 font=("Segoe UI", 10)).pack(side="left")
        e = tk.Entry(row, width=width, font=("Segoe UI", 10), bg="white", relief="solid", bd=1, show=show)
        e.pack(side="left", padx=8)
        if default:
            e.insert(0, default)
        return e

    def _refresh_email_subject():
        email_status.config(text="", fg="#333333")
        new_firma, _ = extract_firma_data(_cur_kasse_ordner)
        pc_name = platform.node()
        datum = datetime.now().strftime('%d.%m.%Y')
        f_parts = ""
        if new_firma:
            f_name = (new_firma.get("fabetrieb") or "").strip()
            f_plz = (new_firma.get("fafirmaplz") or "").strip()
            f_ort = (new_firma.get("faort") or "").strip()
            f_plzort = " ".join(p for p in [f_plz, f_ort] if p)
            f_parts = ", ".join(p for p in [f_name, f_plzort] if p)
        new_subject = f"PC-Informationen / {f_parts} / {pc_name}, {datum}" if f_parts else f"PC-Informationen / {pc_name}, {datum}"
        smtp_subject.delete(0, tk.END)
        smtp_subject.insert(0, new_subject)
        defaults = {
            smtp_server: "asmtp.mail.hostpoint.ch",
            smtp_port: "465",
            smtp_user: "mailservice@keller-duerr.ch",
            smtp_from: "mailservice@keller-duerr.ch",
        }
        for field, val in defaults.items():
            if isinstance(field, tk.Entry):
                field.delete(0, tk.END)
                field.insert(0, val)
            else:
                field.set(val)
        if isinstance(smtp_pass, tk.Entry):
            smtp_pass.delete(0, tk.END)
            smtp_pass.insert(0, "kasseX3000kd")
        else:
            smtp_pass.set("kasseX3000kd")
        enc_var.set("ssl")

    add_section_title(scroll_frame, "E-Mail Versand", top_padding=20, on_refresh=_refresh_email_subject)

    email_recipients = [
        ("Keller & Dürr allgemein", "office@keller-duerr.ch"),
        ("Daniel Büchel", "d.buechel@keller-duerr.ch"),
        ("Andreas Büchel", "a.buechel@keller-duerr.ch"),
        ("Alexander Baumgartner", "a.baumgartner@keller-duerr.ch"),
        ("Lukas Sonderegger", "l.sonderegger@keller-duerr.ch"),
    ]

    def _on_cb_select(*args):
        sel = cb_var.get()
        for name, email in email_recipients:
            if sel == name:
                smtp_to.delete(0, tk.END)
                smtp_to.insert(0, email)
                break

    cb_row = tk.Frame(scroll_frame, bg="white")
    cb_row.pack(fill="x", padx=30, pady=5)
    tk.Label(cb_row, text="Empfänger wählen", width=16, anchor="w", bg="white", fg="#444444",
             font=("Segoe UI", 10)).pack(side="left")
    cb_display = [name for name, _ in email_recipients]
    cb_var = tk.StringVar(value="Keller & Dürr allgemein")
    cb_var.trace_add("write", _on_cb_select)
    recipient_cb = tk.OptionMenu(cb_row, cb_var, *cb_display)
    recipient_cb.config(width=40, font=("Segoe UI", 14), bg="white", fg="#333333", activebackground="#0078d4", activeforeground="white", bd=1, relief="solid", anchor="w")
    recipient_cb["menu"].config(font=("Segoe UI", 14), bg="white", fg="#333333", activebackground="#0078d4", activeforeground="white")
    recipient_cb.pack(side="left", padx=8)

    smtp_to = add_email_row(scroll_frame, "Empfänger", default="office@keller-duerr.ch")
    if not password_ok:
        smtp_to.master.pack_forget()
    default_subject = f"PC-Informationen / {platform.node()}, {datetime.now().strftime('%d.%m.%Y')}"
    smtp_subject = add_email_row(scroll_frame, "Betreff", default=default_subject)
    if kasse_firma_data:
        f_name = (kasse_firma_data or {}).get("fabetrieb", "").strip()
        f_plz = (kasse_firma_data or {}).get("fafirmaplz", "").strip()
        f_ort = (kasse_firma_data or {}).get("faort", "").strip()
        f_plzort = " ".join(p for p in [f_plz, f_ort] if p)
        f_parts = ", ".join(p for p in [f_name, f_plzort] if p)
        new_subject = f"PC-Informationen / {f_parts} / {platform.node()}, {datetime.now().strftime('%d.%m.%Y')}"
        smtp_subject.delete(0, tk.END)
        smtp_subject.insert(0, new_subject)

    attach_frame = tk.Frame(scroll_frame, bg="white")
    attach_frame.pack(fill="x", padx=30, pady=(10, 5))
    tk.Label(attach_frame, text="Anhänge", width=16, font=("Segoe UI", 10), fg="#444444", bg="white",
             anchor="w").pack(side="left")
    sys_info_var = tk.BooleanVar(value=False)
    tk.Label(attach_frame, text="☑ Allgemeine PC-Informationen", fg="#aaaaaa", bg="white",
             font=("Segoe UI", 10)).pack(side="left", padx=(8, 20))
    tk.Checkbutton(attach_frame, text="Komplette Systeminformationen", variable=sys_info_var,
                   bg="white", font=("Segoe UI", 10)).pack(side="left")

    if password_ok:
        smtp_server = add_email_row(scroll_frame, "SMTP Server", default="asmtp.mail.hostpoint.ch")
        smtp_port = add_email_row(scroll_frame, "Port", default="465")
        smtp_user = add_email_row(scroll_frame, "Benutzername", default="mailservice@keller-duerr.ch")
        smtp_pass = add_email_row(scroll_frame, "Passwort", show="\u25CF", default="kasseX3000kd")
        smtp_from = add_email_row(scroll_frame, "Absender", default="mailservice@keller-duerr.ch")

        enc_row = tk.Frame(scroll_frame, bg="white")
        enc_row.pack(fill="x", padx=30, pady=5)
        tk.Label(enc_row, text="Verschlüsselung", width=16, anchor="w", bg="white", fg="#444444",
                 font=("Segoe UI", 10)).pack(side="left")
        enc_var = tk.StringVar(value="ssl")
        for val, txt in [("ssl", "SSL/TLS"), ("starttls", "STARTTLS"), ("none", "Keine")]:
            tk.Radiobutton(enc_row, text=txt, variable=enc_var, value=val, bg="white",
                           font=("Segoe UI", 10)).pack(side="left", padx=(0, 15))
    else:
        smtp_server = tk.StringVar(value="asmtp.mail.hostpoint.ch")
        smtp_port = tk.StringVar(value="465")
        smtp_user = tk.StringVar(value="mailservice@keller-duerr.ch")
        smtp_pass = tk.StringVar(value="kasseX3000kd")
        smtp_from = tk.StringVar(value="mailservice@keller-duerr.ch")
        enc_var = tk.StringVar(value="ssl")

    email_status = tk.Label(scroll_frame, text="", font=("Segoe UI", 10), fg="#333333", bg="white", anchor="w",
                            wraplength=820, justify="left")

    def _set_email_status(msg, color="#333333"):
        email_status.config(text=msg, fg=color)

    def send_email():
        for val, name in [(smtp_server, "SMTP Server"), (smtp_port, "Port"),
                          (smtp_user, "Benutzername"), (smtp_pass, "Passwort"),
                          (smtp_from, "Absender"), (smtp_to, "Empfänger")]:
            if not val.get().strip():
                _set_email_status(f"❌ {name} darf nicht leer sein.", "#d32f2f")
                return

        _set_email_status("Sende E-Mail …", "#333333")

        def worker():
            def status(msg, color="#333333"):
                root.after(0, lambda: _set_email_status(msg, color))
            try:
                status("Erstelle Bericht …")
                report = gather_report_data()

                sys_path = None
                if sys_info_var.get():
                    status("Generiere Systeminformationen …")
                    sys_path = create_system_info_text(report)

                status("Erstelle PC-Informationen …")
                file_path = create_pc_infos_text(report)

                import smtplib
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart
                from email.mime.base import MIMEBase
                from email import encoders

                status("Verbinde mit SMTP-Server …")
                msg = MIMEMultipart()
                msg["From"] = smtp_from.get().strip()
                msg["To"] = smtp_to.get().strip()
                msg["Subject"] = smtp_subject.get().strip() or f"PC-Informationen / {platform.node()}, {datetime.now().strftime('%d.%m.%Y')}"

                with open(file_path, "rb") as f:
                    attachment = MIMEBase("application", "octet-stream")
                    attachment.set_payload(f.read())
                encoders.encode_base64(attachment)
                attachment.add_header("Content-Disposition",
                                      f"attachment; filename={os.path.basename(file_path)}")
                msg.attach(attachment)

                if sys_path and os.path.isfile(sys_path):
                    with open(sys_path, "rb") as f:
                        sys_att = MIMEBase("application", "octet-stream")
                        sys_att.set_payload(f.read())
                    encoders.encode_base64(sys_att)
                    sys_att.add_header("Content-Disposition",
                                       f"attachment; filename={os.path.basename(sys_path)}")
                    msg.attach(sys_att)

                msg.attach(MIMEText("Siehe Anhang.", "plain", "utf-8"))

                port = int(smtp_port.get().strip())
                enc = enc_var.get()
                host = smtp_server.get().strip()

                if enc == "ssl":
                    server = smtplib.SMTP_SSL(host, port, timeout=15)
                else:
                    server = smtplib.SMTP(host, port, timeout=15)
                    if enc == "starttls":
                        status("Aktiviere STARTTLS …")
                        server.starttls()

                status("Melde an …")
                server.login(smtp_user.get().strip(), smtp_pass.get().strip())
                status("Sende Nachricht …")
                server.send_message(msg)
                server.quit()
                status("✅ E-Mail erfolgreich gesendet!", "#28a745")
            except Exception as exc:
                status(f"❌ Fehler: {exc}", "#d32f2f")

        threading.Thread(target=worker, daemon=True).start()

    btn_email = tk.Button(scroll_frame, text="E-Mail senden", bg="#0078d4", fg="white",
              font=("Segoe UI", 11, "bold"), width=22, height=1, state="disabled",
              relief="flat", command=send_email)
    btn_email.pack(anchor="w", padx=30, pady=(10, 2))
    email_status.pack(anchor="w", padx=30, pady=(0, 5))

    tk.Frame(scroll_frame, bg="white", height=15).pack()

    add_section_title(scroll_frame, "Textdatei erstellen", top_padding=5)

    text_status_label = tk.Label(
        scroll_frame,
        text="",
        bg="white",
        font=("Segoe UI", 11),
        fg="#333333",
        justify="left",
        anchor="w",
        wraplength=820,
    )

    def gather_report_data():
        ip_text = ip_labels["primary"].cget("text")
        ext_label = ip_labels["extended"]
        if ext_label is not None and ext_label.winfo_ismapped():
            extended = ext_label.cget("text")
            if extended:
                ip_text = ip_text + f"\nErweiterte Netzwerke: {extended}"

        vlan_rows = []
        for item in tree2_primary.get_children():
            vlan_rows.append(tree2_primary.item(item, "values"))
        for item in tree2_extended.get_children():
            vlan_rows.append(tree2_extended.item(item, "values"))

        return {
            "erstellt_am": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "admin": is_admin(),
            "output_path": get_text_output_path(_cur_kasse_firma_data),
            "netzwerkeinstellungen": [
                ("PC Name", platform.node()),
                ("IP-Adresse", ip_text),
                ("Subnetz", info_labels["Subnetz"].cget("text")),
                ("Gateway", info_labels["Gateway"].cget("text")),
                ("DNS1", info_labels["DNS1"].cget("text")),
                ("DNS2", info_labels["DNS2"].cget("text")),
                ("Interface", info_labels["Interface"].cget("text")),
                ("DHCP", info_labels["DHCP"].cget("text")),
                ("Firewall (Privat)", fw_private_label.cget("text")),
                ("Firewall (Öffentlich)", fw_public_label.cget("text")),
            ],
            "netzwerk_eingaben": [
                ("IP", entries["IP"].get().strip()),
                ("Subnetz", entries["Subnetz"].get().strip()),
                ("Gateway", entries["Gateway"].get().strip()),
                ("DNS1", entries["DNS1"].get().strip()),
                ("DNS2", entries["DNS2"].get().strip()),
            ],
            "windows": [
                ("PC Name", windows["PC Name"]),
                ("System", f"Windows {windows['Release']}"),
                ("Version", windows["Version"]),
                ("Letztes Update am", last_windows_update),
                ("Letzter Neustart", f"{boot_time} Uhr (Betriebszeit: {uptime_str})"),
            ],
            "drucker": [tuple(tree.item(item, "values")) for item in tree.get_children()],
            "vlan": vlan_rows,
            "kasse": [
                ("Version", vers_label.cget("text")),
                ("Installiert am", install_label.cget("text")),
                ("Kassenordner", ordner_label.cget("text") if _cur_kasse_ordner else "Nicht gefunden"),
                ("Arbeitsstationen", ws_label.cget("text")),
            ],
            "kasse_firma": firma_labels,
            "kasse_betriebsstaette": bs_labels,
            "internet": internet_label.cget("text"),
            "teamviewer": f"ID: {_cur_tv_id} (Öffnen über Button)",
            "anydesk": f"ID: {_cur_anydesk_id} (Öffnen über Button)",
            "benutzer": get_local_users(),
            "datentraeger": get_drive_info(),
        }

    def on_create_text():
        text_status_label.config(text="Textdatei wird erstellt …", fg="#333333")

        def worker():
            try:
                path = create_pc_infos_text(gather_report_data())
                message = f"✅ Textdatei gespeichert:\n{path}"
                color = "#28a745"
            except Exception as exc:
                message = f"❌ Textdatei konnte nicht erstellt werden.\n{benutzer_fehlermeldung(exc)}"
                color = "#d32f2f"
            root.after(0, lambda: text_status_label.config(text=message, fg=color))

        threading.Thread(target=worker, daemon=True).start()

    btn_text = tk.Button(
        scroll_frame,
        text="Textdatei erstellen",
        bg="#0078d4",
        fg="white",
        font=("Segoe UI", 11, "bold"),
        width=22,
        height=1,
        state="disabled",
        relief="flat",
        command=on_create_text,
    )
    btn_text.pack(anchor="w", padx=30, pady=10)
    text_status_label.pack(anchor="w", padx=30, pady=(0, 10))

    # ====================== INFO ======================
    t_info = ttk.Frame(tabs)

    info_main = tk.Frame(t_info, bg="white")
    info_main.pack(fill="both", expand=True, padx=30, pady=25)

    left_col = tk.Frame(info_main, bg="white")
    left_col.pack(fill="both", expand=True)

    tk.Label(left_col, text="KDtool - Keller & Dürr Kassensysteme AG",
             font=("Segoe UI", 14, "bold"), fg="#0078d4", bg="white").pack(anchor="w", pady=(0, 12))

    for line in ("Wegenstrasse 4a", "CH-9436 Balgach", "Schweiz"):
        tk.Label(left_col, text=line, font=("Segoe UI", 10), fg="#333333", bg="white").pack(anchor="w")

    tk.Label(left_col, text="", bg="white").pack(pady=6)

    phone_label = tk.Label(left_col, text="Telefon: 081 756 45 72",
                           font=("Segoe UI", 10), fg="#0078d4", bg="white", cursor="hand2")
    phone_label.pack(anchor="w")
    phone_label.bind("<Button-1>", lambda e: webbrowser.open("tel:+41817564572"))

    email_label = tk.Label(left_col, text="info@keller-duerr.ch",
                           font=("Segoe UI", 10), fg="#0078d4", bg="white", cursor="hand2")
    email_label.pack(anchor="w")
    email_label.bind("<Button-1>", lambda e: webbrowser.open("mailto:info@keller-duerr.ch"))

    tk.Label(left_col, text="", bg="white").pack(pady=10)

    tk.Label(left_col, text="Programminformationen",
             font=("Segoe UI", 11, "bold"), fg="#0078d4", bg="white").pack(anchor="w", pady=(0, 5))

    tk.Label(left_col, text="KDtool",
             font=("Segoe UI", 10, "bold"), fg="#333333", bg="white").pack(anchor="w")

    tk.Label(left_col, text=f"Version: {version_str}",
             font=("Segoe UI", 10), fg="#333333", bg="white").pack(anchor="w", pady=(2, 0))

    tk.Label(left_col, text="", bg="white").pack(pady=6)

    tk.Label(left_col, text="Alternative Update-URL (optional):",
             font=("Segoe UI", 9), fg="#555555", bg="white").pack(anchor="w")

    update_url_entry = tk.Entry(left_col, font=("Segoe UI", 9), bg="white", fg="#333333",
                                relief="solid", bd=1, width=60)
    update_url_entry.pack(anchor="w", pady=(3, 0))

    update_status = tk.Label(left_col, text="", font=("Segoe UI", 9), fg="#555555", bg="white", anchor="w")

    update_sources = [
        ("https://raw.githubusercontent.com/soendi/KDtool/main", "KDtool.exe"),
        ("https://www.keller-duerr.ch/kdtool", "kdtool.exe"),
    ]

    def _try_fetch(url):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        return urllib.request.urlopen(req, timeout=10).read().decode("utf-8").strip()

    def _try_download(url, dest):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
            f.write(r.read())

    def check_for_updates():
        update_status.pack(anchor="w", pady=(8, 0))
        update_status.config(text="Prüfe auf Updates …", fg="#555555")

        def worker():
            custom = update_url_entry.get().strip()
            if custom and not custom.startswith("http://") and not custom.startswith("https://") and not custom.startswith("file://"):
                custom = "file:///" + custom.replace("\\", "/").lstrip("/")
            bases = [(custom, "KDtool.exe")] if custom else []
            bases += update_sources
            for base, exe_name in bases:
                try:
                    base = base.rstrip("/")
                    latest = _try_fetch(f"{base}/version.txt")
                    if int(latest) > int(version_str):
                        def confirm_and_update(b=base, exe=exe_name, v=latest):
                            if not messagebox.askyesno("Update verfügbar", f"Version {v} ist verfügbar.\nJetzt herunterladen und installieren?"):
                                return
                            update_status.config(text="Lade Update herunter …", fg="#555555")
                            threading.Thread(target=perform_update, args=(v, f"{b}/{exe}"), daemon=True).start()
                        root.after(0, lambda: [
                            update_status.config(text=f"Version {latest} verfügbar!", fg="#28a745"),
                            info_update_btn.config(text="Jetzt aktualisieren", command=confirm_and_update, state="normal")
                        ])
                        return
                    else:
                        root.after(0, lambda: update_status.config(text="Sie haben die aktuelle Version.", fg="#28a745"))
                        return
                except Exception:
                    continue
            root.after(0, lambda: update_status.config(
                text="Update-Prüfung fehlgeschlagen." + (" Alternative URL wird verwendet." if not custom else ""), fg="#d32f2f"))

        threading.Thread(target=worker, daemon=True).start()

    def _launch_update(dl_path, current, latest, status_label):
        kernel32 = ctypes.windll.kernel32
        bak_path = os.path.join(tempfile.gettempdir(), "KDtool.exe.update_bak")
        try:
            os.remove(bak_path)
        except:
            pass
        kernel32.MoveFileW(current, bak_path)
        try:
            import shutil
            shutil.copy2(dl_path, current)
        except Exception:
            shutil.copy2(bak_path, current)
        root.after(0, lambda: (messagebox.showinfo("Update erfolgreich", "Update erfolgreich, bitte das Programm neu starten."), root.destroy()))

    def perform_update(latest, download_url):
        try:
            temp_dir = os.path.join(os.environ.get("TEMP", "C:\\Windows\\Temp"), "kd-update")
            os.makedirs(temp_dir, exist_ok=True)
            current = os.path.abspath(sys.argv[0])
            if download_url.startswith("file:///"):
                from urllib.request import url2pathname
                dl_path = url2pathname(download_url[8:])
            else:
                dl_path = os.path.join(temp_dir, "KDtool_new.exe")
                _try_download(download_url, dl_path)
            _launch_update(dl_path, current, latest, update_status)
        except Exception as exc:
            root.after(0, lambda: update_status.config(text=f"Update fehlgeschlagen: {benutzer_fehlermeldung(exc)}", fg="#d32f2f"))

    info_update_btn = tk.Button(
        left_col, text="Nach Updates suchen", font=("Segoe UI", 10), bg="#0078d4", fg="white",
        relief="flat", padx=12, pady=4, command=check_for_updates,
    )
    info_update_btn.pack(anchor="w", pady=(8, 0))

    # ====================== ZIP-UPDATE ======================
    tk.Label(left_col, text="", bg="white").pack(pady=12)

    tk.Label(left_col, text="Lokales Update: ZIP-Datei muss KDtool.exe und Version.txt enthalten.",
             font=("Segoe UI", 9, "bold"), fg="#555555", bg="white", anchor="w", wraplength=600,
             justify="left").pack(anchor="w")

    zip_update_status = tk.Label(left_col, text="", font=("Segoe UI", 9), fg="#555555", bg="white", anchor="w")

    def process_zip_file(zip_path):
        try:
            import zipfile
            with zipfile.ZipFile(zip_path, 'r') as z:
                names = [n.replace("\\", "/") for n in z.namelist()]
                if 'version.txt' not in names:
                    zip_update_status.config(text="ZIP enthält keine version.txt.", fg="#d32f2f")
                    return
                latest = z.read('version.txt').decode('utf-8').strip()
                if int(latest) <= int(version_str):
                    zip_update_status.config(text=f"Version {latest} ist nicht neuer als aktuell ({version_str}).", fg="#d32f2f")
                    return
                exe_key = next((n for n in names if n.lower().endswith("kdtool.exe")), None)
                if not exe_key:
                    zip_update_status.config(text="ZIP enthält keine kdtool.exe.", fg="#d32f2f")
                    return
                if not messagebox.askyesno("Update verfügbar", f"Version {latest} in ZIP-Datei.\nJetzt installieren?"):
                    return
                zip_update_status.config(text="Extrahiere und installiere Update …", fg="#555555")
                temp_dir = os.path.join(os.environ.get("TEMP", "C:\\Windows\\Temp"), "kd-update")
                os.makedirs(temp_dir, exist_ok=True)
                dl_path = os.path.join(temp_dir, "KDtool_new.exe")
                z.extract(exe_key, temp_dir)
                extracted = os.path.join(temp_dir, exe_key.replace("/", "\\"))
                if os.path.exists(extracted) and extracted != dl_path:
                    os.replace(extracted, dl_path)
                current = os.path.abspath(sys.argv[0])
                _launch_update(dl_path, current, latest, zip_update_status)
        except Exception as exc:
            zip_update_status.config(text=f"Fehler: {benutzer_fehlermeldung(exc)}", fg="#d32f2f")

    def select_zip():
        path = filedialog.askopenfilename(
            title="ZIP-Datei auswählen",
            filetypes=[("ZIP-Dateien", "*.zip"), ("Alle Dateien", "*.*")]
        )
        if path:
            zip_update_status.pack(anchor="w", pady=(6, 0))
            process_zip_file(path)

    tk.Button(left_col, text="ZIP-Datei auswählen …", font=("Segoe UI", 10), bg="#0078d4", fg="white",
              relief="flat", padx=12, pady=4, command=select_zip,
              ).pack(anchor="w", pady=(8, 0))

    # Tab-Reihenfolge festlegen
    _add_tab(t1, text="Netzwerkeinstellungen")
    _add_tab(t4, text="Netzwerkgeräte")
    _add_tab(t3, text="Drucker")
    _add_tab(t2, text="Windows")
    _add_tab(t6, text="Internet")
    _add_tab(t7, text="Fernwartung")
    _add_tab(t5, text="Kasse")
    _add_tab(t8, text="Daten übermitteln")
    _add_tab(t_info, text="Info")
    if password_ok:
        _add_tab(t_cleanup, text="Datenträgerbereinigung")
        _add_tab(t_zusatz, text="Zusatzfunktionen")

        # ====================== HOSTS ======================
        t_hosts = ttk.Frame(tabs)
        _add_tab(t_hosts, text="Hosts")
        hosts_path = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"),
                                  "System32", "drivers", "etc", "hosts")

        def _refresh_hosts():
            hosts_text.delete("1.0", "end")
            try:
                with open(hosts_path, "r") as f:
                    hosts_text.insert("1.0", f.read())
            except Exception:
                hosts_text.insert("1.0", f"# Fehler beim Lesen von {hosts_path}")

        add_section_title(t_hosts, "Hosts", top_padding=20, on_refresh=_refresh_hosts)
        hosts_text = tk.Text(t_hosts, font=("Consolas", 10), bg="white", fg="#222222",
                             relief="solid", bd=1, wrap="none")
        hosts_text.pack(fill="both", expand=True, padx=20, pady=10)

        try:
            with open(hosts_path, "r") as f:
                hosts_text.insert("1.0", f.read())
        except Exception:
            hosts_text.insert("1.0", f"# Fehler beim Lesen von {hosts_path}")

        def save_hosts():
            try:
                with open(hosts_path, "w") as f:
                    f.write(hosts_text.get("1.0", "end-1c"))
                hosts_status.config(text="✅ Hosts-Datei wurde gespeichert", fg="#28a745")
            except Exception as e:
                txt = "❌ Adminrechte erforderlich" if "permission" in str(e).lower() or "zugriff verweigert" in str(e).lower() else f"❌ Fehler: {e}"
                hosts_status.config(text=txt, fg="#d32f2f")

        tk.Button(t_hosts, text="Hosts speichern", bg="#0078d4", fg="white",
                  font=("Segoe UI", 11, "bold"), relief="flat", padx=16, pady=6,
                  state="normal" if is_admin() else "disabled",
                  command=save_hosts).pack(anchor="e", padx=20, pady=(10, 2))
        hosts_status = tk.Label(t_hosts, text="", font=("Segoe UI", 10), bg="white", anchor="e")
        hosts_status.pack(anchor="e", padx=20, pady=(0, 10))

    _update_tab_colors()

    bottom_bar = tk.Frame(root, bg="white")
    bottom_bar.pack(fill="x", padx=15, pady=(5, 8))

    tk.Label(bottom_bar, text=datetime.now().strftime("%d.%m.%Y"),
             font=("Segoe UI", 9), fg="#555555", bg="white").pack(side="left")
    tk.Label(bottom_bar, text=f"Version {version_str}",
             font=("Segoe UI", 9), fg="#555555", bg="white"
             ).place(relx=0.5, rely=0.5, anchor="center")

    right_frame = tk.Frame(bottom_bar, bg="white")
    right_frame.pack(side="right")
    if is_admin():
        tk.Label(right_frame, text="✓ Administrator-Modus aktiv", fg="green", bg="white",
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 10))
    else:
        tk.Label(right_frame, text="⚠ Keine Administrator-Rechte!", fg="red", bg="white",
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 10))
    if password_ok:
        tk.Label(right_frame, text="✓ K&D Modus aktiv", fg="green", bg="white",
                 font=("Segoe UI", 9, "bold")).pack(side="left")
    else:
        tk.Label(right_frame, text="✗ K&D Modus aus", fg="red", bg="white",
                 font=("Segoe UI", 9, "bold")).pack(side="left")

    def on_closing():
        global app_running
        app_running = False
        stop_event.set()
        try:
            os.remove(NETWORK_BACKUP_FILE)
        except:
            pass
        try:
            sysinfo_path = os.path.join(os.path.dirname(get_text_output_path()), "Systeminformationen.txt")
            os.remove(sysinfo_path)
        except:
            pass
        slide_out(root, on_done=root.destroy)

    root.protocol("WM_DELETE_WINDOW", on_closing)
    slide_in(root, 1380, 1000)
    set_titlebar_style(root)

    def _check_startup_update():
        sources = [
            ("https://raw.githubusercontent.com/soendi/KDtool/main", True, "KDtool.exe"),
            ("https://www.keller-duerr.ch/kdtool", True, "kdtool.exe"),
            ("C:\\Users\\sonde\\Desktop", False, "KDtool.exe"),
        ]
        for base, is_remote, exe_name in sources:
            try:
                if is_remote:
                    req = urllib.request.Request(f"{base}/version.txt", headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        latest = resp.read().decode("utf-8").strip()
                    dl_url = f"{base}/{exe_name}"
                else:
                    vp = os.path.join(base, "version.txt")
                    if not os.path.isfile(vp):
                        continue
                    with open(vp) as f:
                        latest = f.read().strip()
                    dl_url = "file:///" + os.path.join(base, exe_name).replace("\\", "/")
                if int(latest) > int(version_str):
                    root.after(0, lambda v=latest, u=dl_url: (
                        messagebox.showinfo("Update gefunden", "Update gefunden, das Update wird automatisch installiert."),
                        threading.Thread(target=perform_update, args=(v, u), daemon=True).start()
                    ))
                    return
            except:
                continue

    root.after(500, _check_startup_update)


if __name__ == "__main__":
    show_loading_gui()
