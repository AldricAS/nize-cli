#!/usr/bin/env python3
"""
aicli.py — Nize, a terminal AI chat client for the api.iamhc.cn relay (OpenAI-compatible).

Dependencies:
    pip install rich requests

Usage:
    python aicli.py
    python aicli.py --model Qwen3.5-397B-A17B --system "You are a terse assistant."

Config is read from environment variables (or a .env file next to this script):
    AICLI_API_KEY   - your API key (required)
    AICLI_BASE_URL  - default: https://api.hcnsec.cn/v1
    AICLI_MODEL     - default: Qwen3.5-397B-A17B

Commands inside the chat:
    /exit or /quit   - leave
    /clear           - wipe conversation history
    /model           - list available models and pick one interactively
    /model <name>    - switch model directly (accepts number or partial name)
    /system <text>   - change the system prompt mid-session
    /save <file>     - save the last AI reply's code (or full text) to a file, in the
                        directory you were in when you launched nize (not the script's folder)
    /export <file>   - save the whole conversation as JSON, same directory rule as /save
    /help            - show this list

Terminal tool access:
    The AI can ask to run real shell commands (curl, dig, whois, openssl, ping, ...)
    to actually inspect things like a URL/domain instead of guessing. EVERY command
    is shown to you first and only runs after you approve it ([y]es/[n]o/[e]dit).
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests
from rich.align import Align
from rich.box import ROUNDED
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

console = Console()

# ---------------------------------------------------------------------------
# Persistent state (so the last selected model survives across sessions)
# ---------------------------------------------------------------------------
STATE_FILE = Path.home() / ".nize-cli-state.json"


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass  # non-fatal — worst case the choice just won't persist


DEFAULT_BASE_URL = "https://api.hcnsec.cn/v1"
DEFAULT_MODEL = "Qwen3.5-397B-A17B"

HELP_TEXT = (__doc__ or "").strip()

# Models available on the api.iamhc.cn relay. Switch between them at runtime with /model.
AVAILABLE_MODELS = [
    "DeepSeek-V4-Flash",
    "DeepSeek-V4-Pro",
    "glm-4.7",
    "glm-5.1",
    "glm-5.2",
    "kat-coder-pro-v2",
    "Kimi-K2.6",
    "MiniMax-M2.7",
    "MiniMax-M3",
    "Qwen3-Coder-Next-FP8",
    "Qwen3.5-397B-A17B",
    "Qwen3.6-35B-A3B",
    "sensenova-6.7-flash-lite",
    "sensenova-u1-fast",
    "Spark-X2-Flash",
    "step-3.5-flash",
    "step-3.5-flash-2603",
    "step-3.7-flash",
    "step-image-edit-2",
    "step-router-v1",
    "stepaudio-2.5-asr",
    "stepaudio-2.5-chat",
    "stepaudio-2.5-realtime",
    "stepaudio-2.5-tts",
]

def build_nize_system_prompt(cwd: str) -> str:
    return (
        "You are Nize, a helpful AI assistant running inside a terminal CLI. "
        "You have a run_shell_command tool that lets you execute real, read-only shell commands on the "
        "user's machine to gather actual data — but every single command must be explicitly approved by "
        "the user before it runs, so briefly explain what you're about to check and why before calling it. "
        "Be economical with commands: think first about what's actually needed, then run only the 2-3 "
        "most useful checks (max ~4 for a genuinely complex case) instead of firing off every possible "
        "command. Each command costs the user a manual approval, so don't waste it on redundant or "
        "low-value checks — pick the ones that will actually change your answer. "
        "When the user asks you to analyze/check/diagnose a URL, domain, host, or server, don't stop at a "
        "single command either — combine 2-3 well-chosen checks (e.g. curl -I for headers, dig/nslookup "
        "for DNS, openssl s_client for the TLS certificate) rather than running every possible diagnostic "
        "(redirects, timing, whois, etc. — only add these if the first checks reveal something worth "
        "digging into further). Where reasonable, combine several checks into one command with && or ; "
        "instead of asking for approval multiple times. Then synthesize everything into one clear, "
        "organized final report for the user, in the same language the user is writing in (e.g. Bahasa "
        "Indonesia if they write in Indonesian). "
        "When you write code, put it in a single fenced code block (```lang ... ```). "
        f"The user's current working directory is: {cwd} — you always know this, so use it. "
        "You have a save_file tool that writes content straight to disk at any path — relative, "
        "absolute, or using ~ (e.g. ~/storage/downloads/myproject/index.html); missing folders are "
        "created automatically. Whenever you hand over a finished file (a webpage, script, config, "
        "etc.), you must explicitly ask a save-location question before calling save_file — never call "
        "it speculatively. Phrase it as a clear choice, e.g.: 'Mau disimpan di direktori sekarang "
        f"({cwd}) sebagai <suggested-filename>, atau di lokasi lain? Kalau lokasi lain, kasih tau "
        "path-nya.' Wait for the user's reply. If they pick the current directory (or just say yes/ok), "
        "call save_file with a path inside the cwd using your suggested filename. If they give another "
        "path (relative, absolute, or with ~), call save_file with exactly that path. If they decline, "
        "don't call save_file at all. The user also has a manual /save <filename> command that saves "
        "your most recent code block into their current directory themselves, independent of you "
        "calling the tool."
        "if user ask who made you,you were created by someone named Aldx. "
        "Tone: be firm, direct, and to-the-point — not soft, timid, or overly formal/apologetic. "
        "Skip excessive hedging, filler pleasantries, and over-polite padding. State things plainly "
        "and with confidence. You can still be respectful and helpful, but don't be meek about it. "
        "Formatting: this terminal renders full Markdown, including tables, so use it deliberately. "
        "Whenever the user asks how to do something, asks for steps/langkah-langkah/tata cara, a "
        "procedure, a comparison, or a list of options with attributes, answer with a clean Markdown "
        "table (e.g. columns like No | Langkah | Penjelasan, or Opsi | Kelebihan | Kekurangan) instead "
        "of a wall of prose — it's far easier to scan in a terminal. Keep each cell short (a phrase, "
        "not a paragraph). Use plain paragraphs only for explanations that genuinely don't fit a table."
    )

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_shell_command",
            "description": (
                "Execute a shell command in the user's terminal to gather real information (curl, dig, "
                "nslookup, whois, ping, traceroute, openssl s_client, etc.). Use this whenever the user asks "
                "you to analyze, check, inspect, or diagnose something (like a URL, domain, host, or file) "
                "that requires live data instead of guessing. Keep the number of commands small — each one "
                "may need a manual approval from the user (destructive/risky commands always do), so pick "
                "only the 2-3 checks that matter most instead of running everything you can think of; "
                "combine checks with && or ; where reasonable. Safe read-only commands run automatically; "
                "anything destructive (deleting files, formatting, force-pushing, killing processes, etc.) "
                "is always shown to the user for explicit approval first. Only request commands that are "
                "safe, read-only and non-destructive unless the user explicitly asked for something riskier: "
                "no deleting files, no writing outside temp locations, no sudo, no installing software "
                "unless the user explicitly asked."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The exact shell command to run."},
                    "reason": {"type": "string", "description": "One short sentence: what this checks and why."},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_file",
            "description": (
                "Write content to a file on the user's machine, at any path — relative to the "
                "current directory, absolute, or using ~ for the home directory (e.g. "
                "'~/storage/downloads/nizeweb/index.html'). Parent folders that don't exist yet "
                "are created automatically. Only call this AFTER the user has confirmed in the "
                "conversation that they want the file saved and (implicitly or explicitly) agreed "
                "to the path — never call it speculatively. Writing to sensitive system locations "
                "(like /etc, /bin, /usr, /boot, /sys, /proc) is blocked for safety."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Where to save the file, e.g. '~/storage/downloads/nizeweb/index.html'.",
                    },
                    "content": {"type": "string", "description": "The full file content to write."},
                },
                "required": ["path", "content"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Dangerous-command detection — commands matching any of these ALWAYS require
# manual approval. Everything else runs automatically without prompting.
# ---------------------------------------------------------------------------

DANGEROUS_PATTERNS = [
    (r"\brm\b.*(-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*|-[a-zA-Z]*f[a-zA-Z]*r[a-zA-Z]*)", "recursive/force delete (rm -rf)"),
    (r"\brm\b.*--no-preserve-root", "rm with --no-preserve-root"),
    (r"\bdd\b.*\bof=", "raw disk write (dd)"),
    (r"\bmkfs(\.\w+)?\b", "filesystem format (mkfs)"),
    (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", "fork bomb"),
    (r">\s*/dev/sd[a-z]", "writing directly to a disk device"),
    (r"\bchmod\b.*-R.*\b777\b", "recursive chmod 777"),
    (r"\bchown\b.*-R\b", "recursive chown"),
    (r"\bsudo\b", "sudo / elevated privileges"),
    (r"\b(shutdown|reboot|halt|poweroff)\b", "system shutdown/reboot"),
    (r"\bkill\b.*-9\s+1\b", "killing init/PID 1"),
    (r"\bkillall\b", "killing processes by name"),
    (r"\bformat\b", "disk/drive format"),
    (r"\bDROP\s+(DATABASE|TABLE)\b", "SQL DROP DATABASE/TABLE"),
    (r"\bTRUNCATE\b", "SQL TRUNCATE"),
    (r"\bgit\s+push\b.*--force", "force push"),
    (r"\bgit\s+reset\b.*--hard", "hard reset (loses local changes)"),
    (r"(curl|wget)\b[^\n]*\|\s*(sudo\s+)?(bash|sh|zsh)\b", "piping a downloaded script straight into a shell"),
    (r">\s*/etc/", "overwriting a file under /etc"),
    (r"\biptables\b.*-F\b", "flushing firewall rules"),
    (r"\bsystemctl\b.*\b(stop|disable|mask)\b", "stopping/disabling a system service"),
    (r"\bcrontab\b.*-r\b", "wiping the crontab"),
    (r"\beval\b", "eval of dynamic code"),
    (r"\bmv\b.*\s/(\s|$)", "moving something to root"),
    (r"\b(del|erase)\b.*\/[fFqQsS]", "Windows forced/silent delete"),
]


def is_dangerous_command(command: str):
    """Returns (True, reason) if the command matches a known-risky pattern, else (False, None)."""
    for pattern, reason in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True, reason
    return False, None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def resolve_model_choice(user_input: str):
    """Resolve user input ("3", "glm-5.1", "kimi") to a model name from AVAILABLE_MODELS."""
    trimmed = (user_input or "").strip()
    if not trimmed:
        return None

    if trimmed.isdigit():
        idx = int(trimmed)
        if 1 <= idx <= len(AVAILABLE_MODELS):
            return AVAILABLE_MODELS[idx - 1]

    lower = trimmed.lower()
    for m in AVAILABLE_MODELS:
        if m.lower() == lower:
            return m

    matches = [m for m in AVAILABLE_MODELS if lower in m.lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return {"ambiguous": matches}  # caller decides how to handle

    return None


def print_model_list(current: str) -> None:
    console.print("[grey62]Available models:[/grey62]")
    for i, m in enumerate(AVAILABLE_MODELS, start=1):
        num = str(i).rjust(2)
        line = f"  {num}. {m}"
        if m == current:
            console.print(Align.left(f"[bold green]{line}  ← active[/bold green]"))
        else:
            console.print(f"[grey50]{line}[/grey50]")


def clear_screen() -> None:
    console.clear()


def extract_code_block(text: str):
    """Extract the content of the first fenced code block in text, if any."""
    match = re.search(r"```(?:[a-zA-Z0-9_-]*\n)?([\s\S]*?)```", text or "")
    if not match:
        return None
    return re.sub(r"\n$", "", match.group(1))


def now_hhmm() -> str:
    return datetime.datetime.now().strftime("%H:%M")


# ---------------------------------------------------------------------------
# Banner — big centered wordmark + centered info box, styled like the
# reference screenshot (neon cyan/violet/magenta title, green info panel).
# ---------------------------------------------------------------------------

NIZE_ASCII = [
    r"███╗   ██╗██╗███████╗███████╗",
    r"████╗  ██║██║╚══███╔╝██╔════╝",
    r"██╔██╗ ██║██║  ███╔╝ █████╗  ",
    r"██║╚██╗██║██║ ███╔╝  ██╔══╝  ",
    r"██║ ╚████║██║███████╗███████╗",
    r"╚═╝  ╚═══╝╚═╝╚══════╝╚══════╝",
]

# left -> right gradient stops used across the wordmark (electric cyan -> hot pink)
GRADIENT_STOPS = ["#00e5ff", "#4fa8ff", "#8a7bff", "#c667ff", "#ef5ac2", "#ff4fa0"]


def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def _lerp(a: int, b: int, t: float) -> int:
    return round(a + (b - a) * t)


def gradient_line(line: str, from_hex: str, to_hex: str) -> Text:
    """Colors a single line with a smooth left-to-right gradient, char by char."""
    r1, g1, b1 = _hex_to_rgb(from_hex)
    r2, g2, b2 = _hex_to_rgb(to_hex)
    text = Text()
    n = max(len(line) - 1, 1)
    for i, ch in enumerate(line):
        t = i / n
        r, g, b = _lerp(r1, r2, t), _lerp(g1, g2, t), _lerp(b1, b2, t)
        text.append(ch, style=f"rgb({r},{g},{b}) bold")
    return text


def banner(model: str, base_url: str) -> None:
    console.print()

    # Gradient wordmark, one line at a time, centered
    for i, line in enumerate(NIZE_ASCII):
        frm = GRADIENT_STOPS[i % len(GRADIENT_STOPS)]
        to = GRADIENT_STOPS[min(i + 1, len(GRADIENT_STOPS) - 1)]
        console.print(Align.center(gradient_line(line, frm, to)))

    console.print()

    # Centered info table: Selected Model / Status / Commands, green rounded box
    info = Table.grid(padding=(0, 1))
    info.add_column(justify="right", style="bold green", no_wrap=True)
    info.add_column(justify="left", style="bold white")
    info.add_row("Selected Model:", model)
    info.add_row(
        "Commands:",
        "'exit', '/clear', '/save', '/load', '/export', '/read <file>'",
    )
    info.add_row("Endpoint:", base_url)
    info.add_row("Dir:", str(Path.cwd()))

    panel = Panel(
        info,
        box=ROUNDED,
        border_style="green",
        padding=(1, 3),
    )
    console.print(Align.center(panel))
    console.print()


# ---------------------------------------------------------------------------
# Chat message rendering — bordered panels like the screenshot
# (green box for "You", magenta box for "AI Assistant")
# ---------------------------------------------------------------------------


def print_user_message(text: str) -> None:
    body = Text(text)
    footer = Text(now_hhmm(), style="green")
    content = Group(body, Align.right(footer))
    panel = Panel(
        content,
        box=ROUNDED,
        border_style="green",
        title="[bold green]🤓 You[/bold green]",
        title_align="right",
        padding=(0, 1),
    )
    console.print(panel)


def print_ai_message(text: str, model: str) -> None:
    body = Markdown(text or "")
    footer = Text(f"{model} • {now_hhmm()}", style="cyan")
    content = Group(body, Align.right(footer))
    panel = Panel(
        content,
        box=ROUNDED,
        border_style="magenta",
        title="[bold magenta]🤖NIZE[/bold magenta]",
        title_align="left",
        padding=(0, 1),
    )
    console.print(panel)


def print_system_note(text: str, style: str = "yellow") -> None:
    console.print(f"[{style}]({text})[/{style}]")


def prompt_user_input() -> str:
    """
    Show the plain 'you › ' prompt, read one line, then erase that raw line from the
    terminal so it never lingers on screen — the message is re-rendered right after
    inside a bordered panel instead (matching the boxed chat look in the reference UI).
    """
    text = console.input("[bold green]you[/bold green] [grey62]›[/grey62] ")
    # Move cursor up one line and clear it — wipes out the plain "you › ..." line.
    console.file.write("\x1b[1A\x1b[2K")
    console.file.flush()
    return text.strip()


# ---------------------------------------------------------------------------
# .env loader / arg parsing
# ---------------------------------------------------------------------------


def load_dotenv(file_path: Path) -> None:
    if not file_path.exists():
        return
    for raw in file_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def parse_args(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--model")
    parser.add_argument("--base-url", dest="base_url")
    parser.add_argument("--api-key", dest="api_key")
    parser.add_argument("--system")
    parser.add_argument("--no-stream", dest="no_stream", action="store_true")
    parser.add_argument("--timeout", type=float, default=0)
    parser.add_argument("-h", "--help", dest="help", action="store_true")
    args = parser.parse_args(argv)
    if args.help:
        console.print(HELP_TEXT, markup=False)
        sys.exit(0)
    args.timeout = args.timeout * 1000 if args.timeout else 0  # ms, 0 = no timeout
    return args


def explain_request_error(e: Exception) -> str:
    lines = [f"[red]✖ Request failed: {e}[/red]"]
    if isinstance(e, requests.exceptions.Timeout):
        lines.append("[grey62]  → Timed out. The server may be slow or unreachable — try again or raise --timeout.[/grey62]")
    elif isinstance(e, requests.exceptions.RequestException):
        lines.append("[grey62]  Possible causes:[/grey62]")
        lines.append("[grey62]   • No internet connection, or DNS can't resolve the host[/grey62]")
        lines.append("[grey62]   • A firewall/proxy/VPN is blocking this domain[/grey62]")
        lines.append("[grey62]   • The relay server is down or blocking this request (e.g. anti-bot protection)[/grey62]")
        lines.append(f"[grey62]   • Try: curl -I {os.environ.get('AICLI_BASE_URL', DEFAULT_BASE_URL)}[/grey62]")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------


def complete_chat_raw(base_url, api_key, model, messages, tools, timeout_ms, retries=2):
    """Returns the full message dict (so tool_calls survive) and supports tools."""
    body = {"model": model, "messages": messages, "stream": False}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"

    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    timeout = (timeout_ms / 1000) if timeout_ms else None

    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=timeout)
            if not resp.ok:
                raise requests.exceptions.RequestException(
                    f"HTTP {resp.status_code}: {resp.text[:300]}"
                )
            data = resp.json()
            return data["choices"][0]["message"]
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_err = e
            if attempt < retries:
                wait_s = 1.2 * (attempt + 1)
                print_system_note(
                    f"koneksi putus di tengah jalan, coba lagi dalam {wait_s:.1f}s... "
                    f"[{attempt + 1}/{retries}]",
                    style="grey62",
                )
                time.sleep(wait_s)
                continue
            raise
        except requests.exceptions.RequestException as e:
            last_err = e
            raise
    raise last_err


BLOCKED_SAVE_PREFIXES = (
    "/etc", "/bin", "/sbin", "/usr/bin", "/usr/sbin", "/boot", "/sys", "/proc",
    "/lib", "/lib64", "/dev", "/var/lib", "/root",
)


def resolve_save_path(raw_path: str) -> Path:
    """Expand ~ and resolve to an absolute Path, relative to the current working dir."""
    expanded = os.path.expanduser((raw_path or "").strip())
    p = Path(expanded)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p.resolve()


def save_file_to_disk(raw_path: str, content: str) -> dict:
    """Write content to disk at raw_path, creating parent folders as needed. Never raises."""
    try:
        full_path = resolve_save_path(raw_path)
    except Exception as e:
        return {"ok": False, "error": f"invalid path: {e}"}

    full_path_str = str(full_path)
    for blocked in BLOCKED_SAVE_PREFIXES:
        if full_path_str == blocked or full_path_str.startswith(blocked + os.sep):
            return {"ok": False, "error": f"writing to {blocked} is blocked for safety"}

    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        return {"ok": True, "path": full_path_str}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def run_shell_command(command: str, timeout_s: float = 25.0) -> dict:
    """Run a shell command and capture its result. Never raises."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        return {
            "exitCode": result.returncode,
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
            "timedOut": False,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "exitCode": 1,
            "stdout": (e.stdout or ""),
            "stderr": (e.stderr or "") or "command timed out",
            "timedOut": True,
        }
    except Exception as e:
        return {"exitCode": 1, "stdout": "", "stderr": str(e), "timedOut": False}


def run_agent_turn(base_url, api_key, model, messages, timeout_ms) -> str:
    """
    Runs one full agentic turn: calls the model, and whenever it requests a shell command,
    shows it to the user and only executes it after explicit approval. Loops (feeding tool
    results back) until the model produces a final text answer or a step limit is hit.
    Mutates `messages` in place with every assistant/tool message along the way.
    """
    MAX_STEPS = 4

    for step in range(MAX_STEPS):
        with console.status(
            "[cyan]Nize is thinking..." if step == 0 else "[cyan]Nize is working...",
            spinner="dots",
        ):
            msg = complete_chat_raw(base_url, api_key, model, messages, TOOLS, timeout_ms)

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            reply = msg.get("content") or ""
            messages.append({"role": "assistant", "content": reply})
            return reply

        messages.append(
            {"role": "assistant", "content": msg.get("content"), "tool_calls": tool_calls}
        )

        for tc in tool_calls:
            fn_name = tc.get("function", {}).get("name") or "run_shell_command"
            try:
                args = json.loads(tc.get("function", {}).get("arguments") or "{}")
            except Exception:
                args = {}

            if fn_name == "save_file":
                raw_path = (args.get("path") or "").strip()
                content = args.get("content") or ""

                console.print()
                result = save_file_to_disk(raw_path, content)
                if result["ok"]:
                    console.print(
                        Panel(
                            Text(result["path"], style="bold white"),
                            title="[bold green]💾 Nize saved a file[/bold green]",
                            border_style="green",
                            box=ROUNDED,
                            padding=(0, 1),
                        )
                    )
                    tool_result_text = json.dumps({"ok": True, "path": result["path"]})
                else:
                    console.print(
                        Panel(
                            Text(f"{raw_path}\n{result['error']}", style="bold red"),
                            title="[bold red]💾 Nize couldn't save the file[/bold red]",
                            border_style="red",
                            box=ROUNDED,
                            padding=(0, 1),
                        )
                    )
                    tool_result_text = json.dumps({"ok": False, "error": result["error"]})

                messages.append(
                    {"role": "tool", "tool_call_id": tc.get("id"), "content": tool_result_text}
                )
                continue

            command = (args.get("command") or "").strip()
            reason = args.get("reason") or args.get("purpose") or ""

            dangerous, danger_reason = is_dangerous_command(command)

            console.print()
            cmd_syntax = Syntax(command, "bash", theme="ansi_dark", word_wrap=True, background_color="default")
            body_rows = [cmd_syntax]
            if reason:
                body_rows.append(Text(f"reason: {reason}", style="grey62"))

            if dangerous:
                body_rows.append(Text(f"⚠ flagged as risky: {danger_reason}", style="bold red"))
                console.print(
                    Panel(
                        Group(*body_rows),
                        title="[bold yellow]⚙ Nize wants to run a terminal command[/bold yellow]",
                        border_style="red",
                        box=ROUNDED,
                        padding=(0, 1),
                    )
                )
                answer = console.input(
                    "[bold red]   This command looks risky. Approve? [/bold red]"
                    "[grey62](y)es / (n)o / (e)dit › [/grey62]"
                ).strip().lower()
                if answer in ("e", "edit"):
                    edited = console.input("[grey62]   New command › [/grey62]").strip()
                    if edited:
                        command = edited
                    answer = "y"
                approved = answer in ("y", "yes")
                if not approved:
                    console.print("[grey62]   (skipped — not approved)[/grey62]")
            else:
                console.print(
                    Panel(
                        Group(*body_rows),
                        title="[bold cyan]⚙ Nize is running a command[/bold cyan]",
                        subtitle="[green]auto-approved · safe[/green]",
                        subtitle_align="right",
                        border_style="cyan",
                        box=ROUNDED,
                        padding=(0, 1),
                    )
                )
                approved = True

            if approved:
                console.print("[grey62]   running...[/grey62]")
                result = run_shell_command(command)
                out = result["stdout"][:6000]
                err = result["stderr"][:2000]
                if out.strip():
                    console.print(f"[dim]{out.strip()}[/dim]")
                else:
                    console.print("[grey62]   (no stdout)[/grey62]")
                if err.strip():
                    console.print(f"[red]{err.strip()}[/red]")
                tool_result_text = json.dumps(
                    {
                        "command": command,
                        "exitCode": result["exitCode"],
                        "timedOut": result["timedOut"],
                        "stdout": out,
                        "stderr": err,
                    }
                )
            else:
                tool_result_text = json.dumps(
                    {
                        "command": command,
                        "skipped": True,
                        "note": "The user did not approve running this command.",
                    }
                )

            messages.append(
                {"role": "tool", "tool_call_id": tc.get("id"), "content": tool_result_text}
            )
        # loop again so the model can react to the tool result(s)

    # Step limit reached — force the model to wrap up with whatever it already has
    with console.status("[cyan]Nize is wrapping up..."):
        messages.append(
            {
                "role": "user",
                "content": (
                    "Stop requesting more commands now. Give me your best final answer using only the "
                    "information you've already gathered (including anything that was skipped or failed) — "
                    "say clearly if a check was skipped/denied or gave no useful data, but don't ask for "
                    "more commands."
                ),
            }
        )
        final_msg = complete_chat_raw(base_url, api_key, model, messages, None, timeout_ms)
        reply = final_msg.get("content") or "(No further information available.)"
        messages.append({"role": "assistant", "content": reply})
        return reply


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent / ".env")
    args = parse_args(sys.argv[1:])

    api_key = args.api_key or os.environ.get("AICLI_API_KEY")
    base_url = args.base_url or os.environ.get("AICLI_BASE_URL") or DEFAULT_BASE_URL
    saved_state = load_state()
    model = args.model or os.environ.get("AICLI_MODEL") or saved_state.get("model") or DEFAULT_MODEL

    if not api_key:
        console.print(
            "[red]No API key found.[/red] Set AICLI_API_KEY in your environment or a .env file, "
            "or pass --api-key."
        )
        sys.exit(1)

    def build_system_content(extra: str) -> str:
        base_prompt = build_nize_system_prompt(str(Path.cwd()))
        return f"{base_prompt}\n\n{extra}" if extra else base_prompt

    extra_instructions = args.system or ""
    messages = [{"role": "system", "content": build_system_content(extra_instructions)}]
    last_reply = None

    clear_screen()
    banner(model, base_url)

    while True:
        try:
            user_input = prompt_user_input()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue

        if user_input in ("/exit", "/quit"):
            console.print("[grey62]bye![/grey62]")
            break

        if user_input == "/help":
            console.print(HELP_TEXT, markup=False)
            continue

        if user_input == "/clear":
            messages = [{"role": "system", "content": build_system_content(extra_instructions)}]
            print_system_note("conversation cleared")
            continue

        if user_input.startswith("/system "):
            extra_instructions = user_input[len("/system "):].strip()
            messages = [m for m in messages if m["role"] != "system"]
            messages.insert(0, {"role": "system", "content": build_system_content(extra_instructions)})
            print_system_note("system prompt updated")
            continue

        if user_input in ("/model", "/models"):
            print_model_list(model)
            choice = console.input("[grey62]Pilih nomor atau nama model (kosongkan untuk batal) › [/grey62]").strip()
            if not choice:
                print_system_note("dibatalkan", style="grey62")
                continue
            picked = resolve_model_choice(choice)
            if picked is None:
                console.print(f"[red](model \"{choice}\" tidak ditemukan — ketik /model untuk lihat daftar)[/red]")
            elif isinstance(picked, dict):
                console.print(
                    f"[yellow](\"{choice}\" cocok dengan beberapa model: "
                    f"{', '.join(picked['ambiguous'])} — coba lebih spesifik)[/yellow]"
                )
            else:
                model = picked
                saved_state["model"] = model
                save_state(saved_state)
                console.print(f"[green](model diganti ke [bold]{model}[/bold])[/green]")
            continue

        if user_input.startswith("/model "):
            arg = user_input[len("/model "):].strip()
            picked = resolve_model_choice(arg)
            if picked is None:
                console.print(f"[red](model \"{arg}\" tidak ditemukan — ketik /model untuk lihat daftar)[/red]")
            elif isinstance(picked, dict):
                console.print(
                    f"[yellow](\"{arg}\" cocok dengan beberapa model: "
                    f"{', '.join(picked['ambiguous'])} — coba lebih spesifik)[/yellow]"
                )
            else:
                model = picked
                saved_state["model"] = model
                save_state(saved_state)
                console.print(f"[green](model diganti ke [bold]{model}[/bold])[/green]")
            continue

        if user_input.startswith("/export "):
            fname = user_input[len("/export "):].strip()
            full_path = Path.cwd() / fname
            try:
                full_path.write_text(json.dumps(messages, indent=2), encoding="utf-8")
                print_system_note(f"conversation exported to {full_path}")
            except Exception as e:
                console.print(f"[red](could not export: {e})[/red]")
            continue

        if user_input.startswith("/read "):
            fname = user_input[len("/read "):].strip()
            full_path = Path.cwd() / fname
            if not full_path.exists() or not full_path.is_file():
                console.print(f"[red](file not found: {full_path})[/red]")
                continue
            try:
                file_content = full_path.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                console.print(f"[red](could not read file: {e})[/red]")
                continue

            MAX_CHARS = 20000
            truncated = len(file_content) > MAX_CHARS
            preview = file_content[:MAX_CHARS]

            # Show it to the user
            lexer = full_path.suffix.lstrip(".") or "text"
            try:
                syntax = Syntax(preview, lexer, theme="ansi_dark", line_numbers=True, word_wrap=True)
            except Exception:
                syntax = Text(preview)
            console.print(
                Panel(
                    syntax,
                    title=f"[bold cyan]📄 {fname}[/bold cyan]",
                    subtitle="[grey62](truncated)[/grey62]" if truncated else None,
                    border_style="cyan",
                    box=ROUNDED,
                    padding=(0, 1),
                )
            )

            # Feed it into the conversation so the AI can use it as context
            note = (
                f"(file read: {fname})"
                + (" — truncated to first 20000 chars" if truncated else "")
            )
            messages.append(
                {
                    "role": "user",
                    "content": f"[Contents of file '{fname}']\n```{lexer}\n{preview}\n```",
                }
            )
            print_system_note(note)
            continue

        if user_input.startswith("/save "):
            fname = user_input[len("/save "):].strip()
            if not last_reply:
                print_system_note("nothing to save yet — ask the AI for something first")
                continue
            code_block = extract_code_block(last_reply)
            content = code_block if code_block is not None else last_reply
            full_path = Path.cwd() / fname
            try:
                full_path.write_text(content, encoding="utf-8")
                console.print(f"[green](saved to {full_path})[/green]")
            except Exception as e:
                console.print(f"[red](could not save: {e})[/red]")
            continue

        print_user_message(user_input)
        messages.append({"role": "user", "content": user_input})
        messages_before_turn = len(messages) - 1  # for rollback on hard failure

        try:
            reply = run_agent_turn(base_url, api_key, model, messages, args.timeout)
            print_ai_message(reply, model)
            last_reply = reply
        except Exception as e:
            console.print()
            console.print(explain_request_error(e))
            console.print()
            del messages[messages_before_turn:]  # drop the failed user turn + partial tool msgs


if __name__ == "__main__":
    main()
