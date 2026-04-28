import os
import re
import telnetlib


PROMPT_PATTERNS = [
    re.compile(br"(?:\r?\n)?\s*<[^>\r\n]+>\s*$"),     # user view prompt
    re.compile(br"(?:\r?\n)?\s*\[[^\]\r\n]+\]\s*$"),  # system/interface view prompt
]

CONFIRM_PATTERNS = [
    re.compile(br"\[Y/N\]", re.IGNORECASE),
    re.compile(br"continue\?", re.IGNORECASE),
]


class H3CNatApplyError(RuntimeError):
    pass


def _telnet_enabled() -> bool:
    raw = os.getenv("H3C_FW_ENABLE_TELNET", "").strip().lower()
    if raw:
        return raw in {"1", "true", "yes", "on"}
    env = os.getenv("DJANGO_ENV", "development").strip().lower()
    return env not in {"prod", "production"}


def _write_line(tn: telnetlib.Telnet, line: str) -> None:
    tn.write((line + "\r\n").encode("utf-8"))


def _read_until_prompt(tn: telnetlib.Telnet, timeout: int | float = 8) -> str:
    idx, _, output = tn.expect(PROMPT_PATTERNS, timeout=timeout)
    if idx < 0:
        return (output or b"").decode("utf-8", errors="ignore")
    return (output or b"").decode("utf-8", errors="ignore")


def _read_with_optional_confirm(tn: telnetlib.Telnet, timeout: int | float = 12) -> str:
    chunks = []
    while True:
        idx, _, output = tn.expect(CONFIRM_PATTERNS + PROMPT_PATTERNS, timeout=timeout)
        if output:
            chunks.append(output)
        if idx < 0:
            break
        if idx < len(CONFIRM_PATTERNS):
            tn.write(b"Y\r\n")
            continue
        break
    return b"".join(chunks).decode("utf-8", errors="ignore")


def _load_conn_config() -> dict:
    return {
        "host": os.getenv("H3C_FW_HOST", "").strip(),
        "port": int(os.getenv("H3C_FW_PORT", "23").strip() or "23"),
        "username": os.getenv("H3C_FW_USERNAME", "").strip(),
        "password": os.getenv("H3C_FW_PASSWORD", ""),
        "timeout": int(os.getenv("H3C_FW_TIMEOUT", "8").strip() or "8"),
    }


def _check_cli_error(text: str) -> None:
    lower = text.lower()
    if "error:" in lower or "invalid" in lower or "incomplete command" in lower:
        raise H3CNatApplyError(f"H3C command failed: {text.strip()}")


def _build_nat_server_command(
    protocol: str,
    public_ip: str,
    public_port: str,
    private_ip: str,
    private_port: str,
    *,
    undo: bool,
) -> str:
    prefix = "undo nat server protocol" if undo else "nat server protocol"
    return (
        f"{prefix} {protocol.lower()} global {public_ip} {public_port} "
        f"inside {private_ip} {private_port}"
    )


def _execute_on_interface(interface: str, command: str) -> None:
    if not _telnet_enabled():
        raise H3CNatApplyError("H3C Telnet path is disabled by policy. Set H3C_FW_ENABLE_TELNET=true only in approved environment.")

    cfg = _load_conn_config()
    host = cfg["host"]
    port = cfg["port"]
    username = cfg["username"]
    password = cfg["password"]
    timeout = cfg["timeout"]

    if not host or not username or not password:
        raise H3CNatApplyError("H3C connection config is incomplete. Check H3C_FW_HOST/H3C_FW_USERNAME/H3C_FW_PASSWORD.")

    try:
        tn = telnetlib.Telnet(host, int(port), int(timeout))
    except OSError as exc:
        raise H3CNatApplyError(f"Unable to connect H3C telnet {host}:{port}: {exc}") from exc

    try:
        tn.read_until(b"Username:", timeout=timeout)
        _write_line(tn, username)
        tn.read_until(b"Password:", timeout=timeout)
        _write_line(tn, password)
        _read_until_prompt(tn, timeout=max(4, timeout))

        # Best effort disable paging.
        _write_line(tn, "screen-length disable")
        _read_until_prompt(tn, timeout=2)

        _write_line(tn, "sys")
        _read_until_prompt(tn, timeout=max(4, timeout))

        _write_line(tn, f"interface {interface}")
        _read_until_prompt(tn, timeout=max(4, timeout))

        _write_line(tn, command)
        out = _read_until_prompt(tn, timeout=max(4, timeout))
        _check_cli_error(out)

        _write_line(tn, "return")
        _read_until_prompt(tn, timeout=max(4, timeout))

        _write_line(tn, "save force")
        save_out = _read_with_optional_confirm(tn, timeout=max(8, timeout))
        _check_cli_error(save_out)
    except EOFError as exc:
        raise H3CNatApplyError(f"Telnet session closed unexpectedly: {exc}") from exc
    finally:
        try:
            tn.close()
        except Exception:
            pass


def apply_h3c_nat_mapping(
    interface: str,
    protocol: str,
    public_ip: str,
    public_port: str,
    private_ip: str,
    private_port: str,
) -> None:
    cmd = _build_nat_server_command(
        protocol=protocol,
        public_ip=public_ip,
        public_port=public_port,
        private_ip=private_ip,
        private_port=private_port,
        undo=False,
    )
    _execute_on_interface(interface, cmd)


def remove_h3c_nat_mapping(
    interface: str,
    protocol: str,
    public_ip: str,
    public_port: str,
    private_ip: str,
    private_port: str,
) -> None:
    cmd = _build_nat_server_command(
        protocol=protocol,
        public_ip=public_ip,
        public_port=public_port,
        private_ip=private_ip,
        private_port=private_port,
        undo=True,
    )
    _execute_on_interface(interface, cmd)
