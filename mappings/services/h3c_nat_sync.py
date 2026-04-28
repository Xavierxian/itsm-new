import os
import re
import telnetlib
import time
from dataclasses import dataclass
from typing import Iterable

from django.db import connection, transaction

from logs.utils import log_resource_change_by_type
from mappings.models import PortMapping


NAT_LINE_RE = re.compile(
    r"^\s*nat\s+server\s+protocol\s+(\S+)\s+global\s+(\d{1,3}(?:\.\d{1,3}){3})\s+(\S+)\s+inside\s+(\d{1,3}(?:\.\d{1,3}){3})\s+(\S+)\s*$",
    re.IGNORECASE,
)
ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-9;?]*[ -/]*[@-~]")
INTERFACE_LINE_RE = re.compile(r"^\s*Interface:\s*([^,]+),\s*Protocol:\s*(.+?)\s*$", re.IGNORECASE)
GLOBAL_LINE_RE = re.compile(r"^\s*Global:\s*(\d{1,3}(?:\.\d{1,3}){3})\s*:\s*(\S+)\s*$", re.IGNORECASE)
LOCAL_LINE_RE = re.compile(r"^\s*Local\s*:\s*(\d{1,3}(?:\.\d{1,3}){3})\s*:\s*(\S+)\s*$", re.IGNORECASE)

PROMPT_PATTERNS = [
    re.compile(br"(?:\r?\n)?\s*<[^>\r\n]+>\s*$"),     # user view prompt
    re.compile(br"(?:\r?\n)?\s*\[[^\]\r\n]+\]\s*$"),  # system view prompt
]

MORE_PATTERNS = [
    re.compile(br"-+\s*More\s*-+", re.IGNORECASE),
    re.compile(br"--More--", re.IGNORECASE),
]


class H3CNatSyncError(RuntimeError):
    pass


def _telnet_enabled() -> bool:
    raw = os.getenv("H3C_FW_ENABLE_TELNET", "").strip().lower()
    if raw:
        return raw in {"1", "true", "yes", "on"}
    env = os.getenv("DJANGO_ENV", "development").strip().lower()
    return env not in {"prod", "production"}


@dataclass
class _NatEntry:
    interface: str
    protocol: str
    public_ip: str
    public_port: str
    private_ip: str
    private_port: str


def _decode_bytes(raw: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "gbk", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _normalize_cli_text(text: str) -> str:
    # Remove ANSI control sequences / cursor control artifacts and normalize line endings.
    text = ANSI_ESCAPE_RE.sub("", text)
    text = text.replace("\r", "")
    text = text.replace("\x08", "")
    return text


def _write_line(tn: telnetlib.Telnet, line: str) -> None:
    tn.write((line + "\r\n").encode("utf-8"))


def _expect_prompt(tn: telnetlib.Telnet, timeout: int | float = 6) -> str:
    idx, _, output = tn.expect(PROMPT_PATTERNS, timeout=timeout)
    if idx < 0:
        # Even when prompt isn't matched, return what we got for diagnostics.
        return _decode_bytes(output or b"")
    return _decode_bytes(output or b"")


def _run_command_capture(tn: telnetlib.Telnet, command: str, timeout: int | float = 12) -> str:
    _write_line(tn, command)
    started = time.monotonic()
    last_data_at = started
    chunks: list[bytes] = []
    min_collect_seconds = 0.6

    while time.monotonic() - started < timeout:
        try:
            part = tn.read_very_eager()
        except EOFError:
            break

        now = time.monotonic()
        if part:
            chunks.append(part)
            last_data_at = now
            lower = part.lower()
            if b"more" in lower:
                tn.write(b" ")
        else:
            # If no more data for a short idle window, stop.
            if (now - started) >= min_collect_seconds and (now - last_data_at) >= 0.7:
                break

        # If prompt appears at the end and we have collected enough data, finish.
        data = b"".join(chunks)
        if (now - started) >= min_collect_seconds:
            if any(p.search(data) for p in PROMPT_PATTERNS):
                # small grace period in case device still streams remaining lines
                time.sleep(0.08)
                try:
                    tail = tn.read_very_eager()
                except EOFError:
                    tail = b""
                if tail:
                    chunks.append(tail)
                    last_data_at = time.monotonic()
                elif (time.monotonic() - last_data_at) >= 0.2:
                    break

        time.sleep(0.08)

    return _normalize_cli_text(_decode_bytes(b"".join(chunks)))


def _parse_nat_entries(interface: str, text: str) -> list[_NatEntry]:
    entries: list[_NatEntry] = []
    normalized = _normalize_cli_text(text)
    for raw in normalized.splitlines():
        m = NAT_LINE_RE.match(raw.strip())
        if not m:
            continue
        protocol, public_ip, public_port_raw, private_ip, private_port = m.groups()
        public_port = public_port_raw.strip()

        protocol_value = protocol.upper() if protocol.isalpha() else protocol
        entries.append(
            _NatEntry(
                interface=interface,
                protocol=protocol_value,
                public_ip=public_ip,
                public_port=public_port,
                private_ip=private_ip,
                private_port=private_port,
            )
        )
    return entries


def _normalize_protocol(raw: str) -> str:
    lower = raw.strip().lower()
    if "tcp" in lower:
        return "TCP"
    if "udp" in lower:
        return "UDP"
    return raw.strip().upper() if raw.strip().isalpha() else raw.strip()


def _normalize_interface_key(raw: str) -> str:
    return re.sub(r"[^a-z0-9]", "", raw.strip().lower())


def _parse_display_nat_server_entries(text: str, include_interfaces: set[str] | None = None) -> tuple[list[_NatEntry], dict]:
    entries: list[_NatEntry] = []
    parse_meta = {
        "blocks_total": 0,
        "blocks_by_interface": {},
    }
    include_keys = {_normalize_interface_key(item) for item in include_interfaces} if include_interfaces else None
    current_interface: str | None = None
    current_protocol: str | None = None
    global_ip: str | None = None
    global_port_raw: str | None = None

    for raw in _normalize_cli_text(text).splitlines():
        line = raw.strip()
        if not line:
            continue

        m_iface = INTERFACE_LINE_RE.match(line)
        if m_iface:
            current_interface = m_iface.group(1).strip()
            current_protocol = _normalize_protocol(m_iface.group(2))
            global_ip = None
            global_port_raw = None
            continue

        m_global = GLOBAL_LINE_RE.match(line)
        if m_global and current_interface:
            global_ip = m_global.group(1).strip()
            global_port_raw = m_global.group(2).strip()
            continue

        m_local = LOCAL_LINE_RE.match(line)
        if m_local and current_interface and current_protocol and global_ip and global_port_raw:
            parse_meta["blocks_total"] += 1
            parse_meta["blocks_by_interface"][current_interface] = parse_meta["blocks_by_interface"].get(current_interface, 0) + 1
            if include_keys and _normalize_interface_key(current_interface) not in include_keys:
                continue
            public_port = global_port_raw.strip()
            private_ip = m_local.group(1).strip()
            private_port = m_local.group(2).strip()
            entries.append(
                _NatEntry(
                    interface=current_interface,
                    protocol=current_protocol,
                    public_ip=global_ip,
                    public_port=public_port,
                    private_ip=private_ip,
                    private_port=private_port,
                )
            )
    return entries, parse_meta


def _load_sync_config_from_env() -> dict:
    interfaces = [item.strip() for item in os.getenv("H3C_FW_INTERFACES", "").split(",") if item.strip()]
    return {
        "host": os.getenv("H3C_FW_HOST", "").strip(),
        "port": int(os.getenv("H3C_FW_PORT", "23").strip() or "23"),
        "username": os.getenv("H3C_FW_USERNAME", "").strip(),
        "password": os.getenv("H3C_FW_PASSWORD", ""),
        "timeout": int(os.getenv("H3C_FW_TIMEOUT", "8").strip() or "8"),
        "command_timeout": int(os.getenv("H3C_FW_COMMAND_TIMEOUT", "90").strip() or "90"),
        "interfaces": interfaces,
    }


def _try_disable_paging(tn: telnetlib.Telnet) -> None:
    # H3C variants may accept one of these commands.
    for cmd in ("screen-length disable", "screen-length 0 temporary"):
        _write_line(tn, cmd)
        _expect_prompt(tn, timeout=2)


def _clear_nat_mappings_table() -> int:
    table_name = PortMapping._meta.db_table
    existing_rows = PortMapping.objects.count()
    if existing_rows <= 0:
        return 0

    quoted_table_name = connection.ops.quote_name(table_name)
    with connection.cursor() as cursor:
        if connection.vendor == "mysql":
            cursor.execute(f"TRUNCATE TABLE {quoted_table_name};")
        else:
            cursor.execute(f"DELETE FROM {quoted_table_name};")
            if connection.vendor == "sqlite":
                try:
                    cursor.execute("DELETE FROM sqlite_sequence WHERE name = %s;", [table_name])
                except Exception:
                    pass

    return existing_rows


def sync_h3c_nat_mappings(
    host: str | None = None,
    port: int | None = None,
    username: str | None = None,
    password: str | None = None,
    interfaces: Iterable[str] | None = None,
    timeout: int | None = None,
) -> dict:
    if not _telnet_enabled():
        raise H3CNatSyncError("H3C Telnet sync path is disabled by policy. Set H3C_FW_ENABLE_TELNET=true only in approved environment.")

    cfg = _load_sync_config_from_env()
    host = host if host is not None else cfg["host"]
    port = port if port is not None else cfg["port"]
    username = username if username is not None else cfg["username"]
    password = password if password is not None else cfg["password"]
    timeout = timeout if timeout is not None else cfg["timeout"]
    command_timeout = cfg["command_timeout"]
    interfaces = list(interfaces) if interfaces is not None else list(cfg["interfaces"])

    if not host or not username or not password or not interfaces:
        raise H3CNatSyncError(
            "H3C sync config is incomplete. Check H3C_FW_HOST/H3C_FW_USERNAME/H3C_FW_PASSWORD/H3C_FW_INTERFACES."
        )

    try:
        tn = telnetlib.Telnet(host, int(port), int(timeout))
    except OSError as exc:
        raise H3CNatSyncError(f"Unable to connect H3C telnet {host}:{port}: {exc}") from exc

    try:
        # Login flow (best effort for different prompts).
        tn.read_until(b"Username:", timeout=timeout)
        _write_line(tn, username)
        tn.read_until(b"Password:", timeout=timeout)
        _write_line(tn, password)
        _expect_prompt(tn, timeout=max(4, int(timeout)))

        _try_disable_paging(tn)

        # Enter system view.
        _write_line(tn, "sys")
        _expect_prompt(tn, timeout=max(4, int(timeout)))

        # As requested: enter the first interface first, then use "display nat server"
        # to capture NAT mappings across interfaces.
        seed_interface = interfaces[0]
        _write_line(tn, f"interface {seed_interface}")
        _expect_prompt(tn, timeout=max(4, int(timeout)))

        output = _run_command_capture(tn, "display nat server", timeout=max(20, int(command_timeout)))
        all_entries, parse_meta = _parse_display_nat_server_entries(output, include_interfaces=set(interfaces))

        if not all_entries:
            # Fallback: command alias on some firmware.
            output_retry = _run_command_capture(tn, "dis nat server", timeout=max(20, int(command_timeout)))
            all_entries, parse_meta = _parse_display_nat_server_entries(output_retry, include_interfaces=set(interfaces))

        _write_line(tn, "return")
        _expect_prompt(tn, timeout=max(4, int(timeout)))

        interface_counts: dict[str, int] = {}
        normalized_counts: dict[str, int] = {}
        for item in all_entries:
            key = _normalize_interface_key(item.interface)
            normalized_counts[key] = normalized_counts.get(key, 0) + 1
        for iface in interfaces:
            interface_counts[iface] = normalized_counts.get(_normalize_interface_key(iface), 0)

        # De-duplicate entries by unique key.
        uniq: dict[tuple, _NatEntry] = {}
        for item in all_entries:
            key = (item.interface, item.protocol, item.public_ip, item.public_port, item.private_ip, item.private_port)
            uniq[key] = item
        normalized_entries = list(uniq.values())

        if not normalized_entries:
            raise H3CNatSyncError("No NAT entries were parsed from H3C output; aborted to avoid clearing existing data.")

        cleared_count = _clear_nat_mappings_table()
        if cleared_count:
            log_resource_change_by_type(
                resource_type=PortMapping._meta.label,
                resource_id=f"table:{PortMapping._meta.db_table}",
                action="deleted",
                before_snapshot={
                    "name": f"端口映射表（{PortMapping._meta.db_table}）",
                    "count": cleared_count,
                },
                after_snapshot={},
                changed_fields=[],
            )

        with transaction.atomic():
            PortMapping.objects.bulk_create(
                [
                    PortMapping(
                        interface=item.interface,
                        protocol=item.protocol,
                        public_ip=item.public_ip,
                        public_port=item.public_port,
                        private_ip=item.private_ip,
                        private_port=item.private_port,
                    )
                    for item in normalized_entries
                ],
                batch_size=500,
            )

        return {
            "total": len(normalized_entries),
            "cleared": cleared_count,
            "interfaces": interfaces,
            "interface_counts": interface_counts,
            "parse_meta": parse_meta,
        }
    except EOFError as exc:
        raise H3CNatSyncError(f"Telnet session closed unexpectedly: {exc}") from exc
    finally:
        try:
            tn.close()
        except Exception:
            pass
