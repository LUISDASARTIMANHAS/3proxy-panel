from collections import Counter
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import json
import os
import re
import socket
import subprocess

BASE = Path(__file__).resolve().parent
HOST = "0.0.0.0"
PORT = 8787
PROXY_IP = "192.168.6.253"
LOG_DIR = Path(r"C:\Servers\3proxy\logs")
LOG_PATTERN = re.compile(r"^3proxy\.log(?:\.\d{4}\.\d{2}\.\d{2})?$")
EXPECTED_EXE = r"C:\Servers\3proxy\bin64\3proxy.exe"

SERVICES = [
    {"name": "HTTP Proxy", "port": 3128},
    {"name": "SOCKS5", "port": 1080},
    {"name": "Minecraft TCP 01", "port": 45845},
    {"name": "Minecraft TCP 02", "port": 45846},
    {"name": "Minecraft TCP 03", "port": 45847},
    {"name": "Minecraft TCP 04", "port": 45848},
]


def latest_log():
    try:
        candidates = [
            p for p in LOG_DIR.iterdir()
            if p.is_file() and LOG_PATTERN.fullmatch(p.name)
        ]
        return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None
    except OSError:
        return None


def get_process():
    command = (
        "(Get-CimInstance Win32_Process -Filter \"Name='3proxy.exe'\" "
        "| Select-Object -First 1 ProcessId,ExecutablePath,CommandLine "
        "| ConvertTo-Json -Compress)"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        data = json.loads(result.stdout.strip())
        return data[0] if isinstance(data, list) and data else data
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return None


def check_port(port):
    try:
        with socket.create_connection((PROXY_IP, port), timeout=1):
            return True
    except OSError:
        return False


def get_status():
    process = get_process()
    services = [{**s, "online": check_port(s["port"])} for s in SERVICES]
    executable = process.get("ExecutablePath") if process else None
    log = latest_log()

    return {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "host": socket.gethostname(),
        "proxy_ip": PROXY_IP,
        "process": {
            "running": process is not None,
            "pid": process.get("ProcessId") if process else None,
            "executable": executable,
            "expected_executable": EXPECTED_EXE,
            "path_matches": (
                os.path.normcase(executable) == os.path.normcase(EXPECTED_EXE)
                if executable else False
            )
        },
        "services": services,
        "log": {
            "path": str(log) if log else str(LOG_DIR / "3proxy.log"),
            "exists": log is not None,
            "size": log.stat().st_size if log else None,
            "modified": (
                datetime.fromtimestamp(log.stat().st_mtime)
                .astimezone().isoformat(timespec="seconds") if log else None
            )
        }
    }


def read_logs(limit, query):
    path = latest_log()
    if not path:
        return {"file": None, "items": [], "total": 0,
                "error": "Nenhum arquivo de log reconhecido foi encontrado."}

    try:
        # Os arquivos atuais sÃ£o pequenos; limitar a leitura protege o painel
        # caso um log cresÃ§a muito.
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 2_000_000))
            content = f.read().decode("utf-8", errors="replace")

        lines = content.splitlines()[-5000:]
        if query:
            q = query.casefold()
            lines = [line for line in lines if q in line.casefold()]

        total = len(lines)
        selected = lines[-limit:]
        items = []

        for line in selected:
            fields = {}
            for part in line.strip().split(" | "):
                for match in re.finditer(r"([A-Z_]+)=(.*?)(?=\s+[A-Z_]+=|$)", part.strip()):
                    fields[match.group(1)] = match.group(2).strip()

            items.append({
                "raw": line.strip(),
                "date": fields.get("DATA", ""),
                "time": fields.get("HORA", ""),
                "service": fields.get("SERVICO", ""),
                "port": fields.get("PORTA", ""),
                "status": fields.get("STATUS", ""),
                "user": fields.get("USUARIO", ""),
                "client": fields.get("CLIENTE", ""),
                "destination": fields.get("DESTINO", ""),
                "sent": fields.get("ENVIADO", ""),
                "received": fields.get("RECEBIDO", "")
            })

        return {
            "file": path.name,
            "modified": datetime.fromtimestamp(path.stat().st_mtime)
                .astimezone().isoformat(timespec="seconds"),
            "total": total,
            "returned": len(items),
            "truncated": size > 2_000_000,
            "items": items,
            "error": None
        }
    except OSError:
        return {"file": path.name, "items": [], "total": 0,
                "error": "NÃ£o foi possÃ­vel ler o arquivo de log."}


def get_stats():
    candidates = []
    try:
        candidates = sorted(
            [p for p in LOG_DIR.iterdir()
             if p.is_file() and LOG_PATTERN.fullmatch(p.name)],
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )[:5]
    except OSError:
        pass

    statuses = Counter()
    clients = Counter()
    destinations = Counter()
    hours = Counter()
    sent_total = 0
    received_total = 0
    total = 0
    parsed = 0

    for path in candidates:
        try:
            with path.open("rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - 5_000_000))
                content = f.read().decode("utf-8", errors="replace")
            for line in content.splitlines():
                total += 1
                fields = {}
                for part in line.strip().split(" | "):
                    for match in re.finditer(r"([A-Z_]+)=(.*?)(?=\s+[A-Z_]+=|$)", part.strip()):
                        fields[match.group(1)] = match.group(2).strip()

                if not fields:
                    continue

                parsed += 1
                status = fields.get("STATUS", "Desconhecido")
                statuses[status] += 1

                client = fields.get("CLIENTE", "")
                if client and client != "-":
                    clients[client] += 1

                destination = fields.get("DESTINO", "")
                if destination and destination != "-":
                    destinations[destination] += 1

                date = fields.get("DATA", "")
                hour = fields.get("HORA", "")
                if date and hour:
                    hours[f"{date} {hour[:2]}:00"] += 1

                sent = re.search(r"\d+", fields.get("ENVIADO", ""))
                received = re.search(r"\d+", fields.get("RECEBIDO", ""))
                if sent:
                    sent_total += int(sent.group())
                if received:
                    received_total += int(received.group())
        except (OSError, ValueError):
            continue

    return {
        "files": [p.name for p in candidates],
        "files_count": len(candidates),
        "records": total,
        "parsed_records": parsed,
        "statuses": [{"code": k, "count": v}
                     for k, v in statuses.most_common()],
        "sent_bytes": sent_total,
        "received_bytes": received_total,
        "top_clients": [{"name": k, "count": v}
                        for k, v in clients.most_common(8)],
        "top_destinations": [{"name": k, "count": v}
                             for k, v in destinations.most_common(8)],
        "hourly": [{"hour": k, "count": v}
                   for k, v in sorted(hours.items())[-24:]],
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds")
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/status":
            self.send_json(get_status())
            return

        if parsed.path == "/api/stats":
            self.send_json(get_stats())
            return

        if parsed.path == "/api/logs":
            params = parse_qs(parsed.query)
            try:
                limit = int(params.get("limit", ["100"])[0])
            except ValueError:
                limit = 100
            limit = max(1, min(limit, 200))
            query = params.get("q", [""])[0][:120]
            self.send_json(read_logs(limit, query))
            return

        if parsed.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def send_json(self, data):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        print("[%s] %s" % (self.log_date_time_string(), format % args))


if __name__ == "__main__":
    print("LDA 3proxy Monitor")
    print(f"URL local: http://{HOST}:{PORT}")
    print("Monitoramento somente de leitura. Ctrl+C encerra o painel.")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()

