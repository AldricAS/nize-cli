# Nize — Terminal AI Chat Client

Nize is a single-file Python terminal client (`aicli.py`) for chatting with large language models through an **OpenAI-compatible** API relay. It renders a colorful, boxed chat UI in your terminal (via `rich`), remembers your last-used model, and — most notably — gives the AI an *agentic* ability to run real, user-approved shell commands and save files directly to disk.

This README walks through everything: what the project contains, how each piece works internally, and a full step‑by‑step setup guide, including how to obtain an API key from the configured provider, **api.iamhc.cn**.

---

## Table of Contents

1. [What's in this project](#1-whats-in-this-project)
2. [Features](#2-features)
3. [How it works (architecture)](#3-how-it-works-architecture)
4. [Prerequisites](#4-prerequisites)
5. [Step-by-step installation](#5-step-by-step-installation)
   - [Step 1 — Get the project files](#step-1--get-the-project-files)
   - [Step 2 — Install Python](#step-2--install-python)
   - [Step 3 — Install dependencies](#step-3--install-dependencies)
   - [Step 4 — Get an API key from api.iamhc.cn](#step-4--get-an-api-key-from-apiiamhccn)
   - [Step 5 — Configure the API key](#step-5--configure-the-api-key)
   - [Step 6 — Run it directly](#step-6--run-it-directly)
   - [Step 7 — (Optional) Install as a global `nize` command](#step-7--optional-install-as-a-global-nize-command)
6. [Configuration reference](#6-configuration-reference)
7. [Command-line flags](#7-command-line-flags)
8. [In-chat commands](#8-in-chat-commands)
9. [Available models](#9-available-models)
10. [Agentic tools: shell commands & file saving](#10-agentic-tools-shell-commands--file-saving)
11. [Usage examples](#11-usage-examples)
12. [Running on Android (Termux)](#12-running-on-android-termux)
13. [Troubleshooting](#13-troubleshooting)
14. [Uninstalling](#14-uninstalling)
15. [Security & privacy notes](#15-security--privacy-notes)
16. [About the API provider (api.iamhc.cn)](#16-about-the-api-provider-apiiamhccn)
17. [License](#17-license)
18. [Credits](#18-credits)

---

## 1. What's in this project

| File | Purpose |
|---|---|
| `aicli.py` | The entire application — a ~950-line Python script. Handles the chat loop, terminal rendering, API calls, tool-calling (shell commands / file saving), model switching, and all `/slash` commands. |
| `install.sh` | A Bash installer that copies `aicli.py` onto your `$PATH` as a global command called `nize`, so you can just type `nize` from anywhere. |
| `requirements.txt` | The two Python packages the script depends on: `rich` and `requests`. |

There is no build step, no compiled binary, and no external config file required beyond a couple of environment variables — everything lives in one script.

---

## 2. Features

- **Boxed, colored chat UI** in the terminal using `rich` — green panels for your messages, magenta panels for the AI's replies, full Markdown rendering (tables, code blocks with syntax highlighting, etc.) inside AI replies.
- **Gradient ASCII banner** on startup showing the active model, endpoint, and working directory.
- **OpenAI-compatible backend** — talks to any server implementing the `/v1/chat/completions` endpoint; defaults to `https://api.iamhc.cn/v1`.
- **Model switching at runtime** with `/model`, including fuzzy/partial-name matching and a numbered picker. Your last-picked model is remembered across sessions in `~/.nize-cli-state.json`.
- **Agentic shell tool** — the AI can request to run real shell commands (`curl`, `dig`, `whois`, `ping`, `openssl s_client`, etc.) to inspect a URL, domain, or file instead of guessing. Every command is shown to you before running; risky commands require explicit `(y)es/(n)o/(e)dit` approval.
- **Built-in dangerous-command detector** — patterns like `rm -rf`, `sudo`, `dd`, `mkfs`, force-pushes, `DROP TABLE`, fork bombs, etc. are automatically flagged and always require manual approval, no matter what.
- **File-writing tool (`save_file`)** — the AI can write a finished file (webpage, script, config) straight to disk at a path you confirm, with sensitive system directories (`/etc`, `/bin`, `/boot`, `/root`, …) blocked outright.
- **Conversation utilities** — `/save` (dump the last code block or reply to a file), `/export` (dump the whole conversation as JSON), `/read` (load a local file into the conversation with syntax-highlighted preview), `/clear`, `/system`.
- **Automatic retry** on network timeouts/connection drops (2 retries with backoff) and a friendly, categorized error explainer when a request ultimately fails.
- **.env file support** so you don't have to `export` your API key in every shell session.
- **Cross-platform installer** that works on regular Linux/macOS shells as well as Termux on Android.

---

## 3. How it works (architecture)

```
┌─────────────┐      HTTP POST /chat/completions       ┌────────────────────┐
│  aicli.py   │ ──────────────────────────────────────▶│  api.iamhc.cn/v1   │
│ (terminal)  │◀────────────────────────────────────── │ (OpenAI-compatible)│
└─────┬───────┘        JSON: choices[0].message         └────────────────────┘
      │
      │ if message.tool_calls contains run_shell_command / save_file
      ▼
┌──────────────────────────┐
│ Ask user for approval    │  (auto-approved if the command is judged "safe";
│ (y/n/e) if flagged risky │   always asked if it matches a dangerous pattern)
└──────────┬────────────────┘
           ▼
┌──────────────────────────┐
│ Execute locally with     │
│ subprocess / write file  │
└──────────┬────────────────┘
           ▼
   result fed back to the model as a "tool" message,
   loop continues (max 4 steps) until a final text reply
```

In plain terms: you type a message → it's sent to the chat-completions endpoint along with a system prompt and two tool definitions (`run_shell_command`, `save_file`) → if the model wants to use a tool, Nize shows you exactly what it wants to do and (for anything risky) waits for your approval → the result is fed back to the model → this repeats up to 4 times per turn before Nize forces a final answer.

---

## 4. Prerequisites

Before you start, make sure you have:

| Requirement | Notes |
|---|---|
| A computer or phone with a terminal | Linux, macOS, Windows (via WSL), or Android (via Termux) all work. |
| **Python 3.8+** | The script uses only standard-library modules plus `requests` and `rich` — no exotic syntax, so any reasonably modern Python 3 works. |
| **pip** | To install `rich` and `requests`. |
| Internet access | To reach the API relay and to install packages. |
| An API key from **api.iamhc.cn** | Free to obtain — see [Step 4](#step-4--get-an-api-key-from-apiiamhccn) below. |

---

## 5. Step-by-step installation

### Step 1 — Get the project files

Unzip or copy the project so that `aicli.py`, `install.sh`, and `requirements.txt` sit together in one folder:

```bash
mkdir -p ~/nize-cli && cd ~/nize-cli
# place aicli.py, install.sh, and requirements.txt in this folder
```

### Step 2 — Install Python

Check whether Python 3 is already available:

```bash
python3 --version
```

If it's missing or too old:

- **Debian/Ubuntu:** `sudo apt update && sudo apt install python3 python3-pip`
- **macOS (Homebrew):** `brew install python3`
- **Windows:** install from [python.org](https://www.python.org/downloads/) or use WSL, then follow the Linux instructions inside WSL.
- **Termux (Android):** see [Section 12](#12-running-on-android-termux).

### Step 3 — Install dependencies

From inside the project folder:

```bash
pip install -r requirements.txt
```

This installs the only two dependencies the script needs:

```
rich
requests
```

If `pip` isn't linked to your `python3`, use `python3 -m pip install -r requirements.txt` instead. On some Linux distros you may need `pip3` or `pip install --user -r requirements.txt` if you don't have write access to the system site-packages.

### Step 4 — Get an API key from api.iamhc.cn

`aicli.py` is preconfigured to talk to **`https://api.iamhc.cn/v1`**, a third-party OpenAI-compatible API relay/aggregator that fronts a number of large language models (GLM, Qwen, Kimi, DeepSeek, MiniMax, etc.) behind a single key. To get your own key:

1. Open **https://api.iamhc.cn** in your browser.
2. **Register / log in.** Sign up with an email or an available social login option, and check the box agreeing to the site's User Agreement / Privacy Policy before continuing.
3. Once logged in, you'll land on the account **console/dashboard**, which shows your account info and usage stats.
4. In the left-hand menu, open the **Token Management** page (this is where API keys/tokens are created and listed).
5. Click **Create Token** (sometimes labeled "+ New Token"). Give it a name, and optionally configure restrictions such as an IP allow-list, quota, or expiration date.
6. Click the "eye" icon next to your newly created token to reveal the full key, then copy it. It will typically look like `sk-...`.
7. If you need higher throughput, the site also offers paid subscription tiers (commonly labeled something like *pub / vip / svip*) managed from a "Wallet" section of the dashboard — the free tier already works for light/testing use but is rate-limited and may be slower at peak times.

> **Keep this key secret.** Anyone with it can make requests (and consume quota/credits) on your account. Treat it like a password.
>
> **Note:** because this is a third-party site independent of Anthropic, exact button labels, plans, and pricing can change over time — always check the current state of the site itself, and read its Terms of Service before relying on it for anything important. See [Section 16](#16-about-the-api-provider-apiiamhccn) for more context.

### Step 5 — Configure the API key

You have two options — pick whichever fits your workflow.

**Option A — Environment variable (quick, per-session or permanent):**

```bash
export AICLI_API_KEY="sk-your-key-here"
```

To make this permanent, append that line to your shell's rc file (`~/.bashrc`, `~/.zshrc`, etc.) and reload it:

```bash
echo 'export AICLI_API_KEY="sk-your-key-here"' >> ~/.bashrc
source ~/.bashrc
```

**Option B — `.env` file (no need to touch your shell profile):**

Create a file named `.env` in the **same folder as the script that actually gets executed** (see the important note below), with contents like:

```env
AICLI_API_KEY=sk-your-key-here
AICLI_BASE_URL=https://api.iamhc.cn/v1
AICLI_MODEL=Qwen3.5-397B-A17B
```

`aicli.py` automatically loads this file on startup (only filling in variables that aren't already set in your environment — real environment variables always win over the `.env` file).

> ⚠️ **Important path detail:** the script looks for `.env` next to *its own file location* (`Path(__file__).resolve().parent / ".env"`), **not** your current working directory. That means:
> - If you're running it as `python3 aicli.py` from the project folder, put `.env` in that same project folder.
> - If you installed it globally with `install.sh` (Step 7), the script gets **copied** to somewhere like `~/.local/bin/nize` — so in that case your `.env` needs to live in `~/.local/bin/` (or `$PREFIX/bin` on Termux), not in your original project folder.
>
> If that's inconvenient, Option A (a real environment variable in your shell rc file) is simpler and works regardless of where the script lives.

### Step 6 — Run it directly

From the project folder:

```bash
python3 aicli.py
```

You should see the gradient "NIZE" banner, followed by a green info panel showing the selected model, endpoint, and current directory, and then a `you ›` prompt waiting for your first message.

### Step 7 — (Optional) Install as a global `nize` command

If you'd rather just type `nize` from any directory instead of `python3 /path/to/aicli.py`, run the installer once:

```bash
bash install.sh
```

What it does:

1. Copies `aicli.py` to a directory on your `$PATH` (`~/.local/bin` on regular Linux/macOS, or `$PREFIX/bin` automatically on Termux) and renames it to `nize`.
2. Makes it executable (`chmod +x`).
3. Checks if that install directory is already on your `$PATH`; if not, it appends an `export PATH=...` line to `~/.bashrc` (or `~/.zshrc` if you're using Zsh) automatically.

After it finishes, reload your shell config (or open a new terminal) and just run:

```bash
nize
```

Remember the `.env` path caveat from Step 5 if you use a `.env` file with the globally installed copy.

---

## 6. Configuration reference

All configuration is done through environment variables (settable directly, via your shell rc file, or via a `.env` file):

| Variable | Required | Default | Description |
|---|---|---|---|
| `AICLI_API_KEY` | **Yes** | *(none)* | Your API key/token from the provider. The app refuses to start without one. |
| `AICLI_BASE_URL` | No | `https://api.iamhc.cn/v1` | Base URL of the OpenAI-compatible API. Change this if you switch to a different compatible provider. |
| `AICLI_MODEL` | No | `Qwen3.5-397B-A17B` | Model name to use at startup. Overridden by `--model`, and remembered across runs once you switch with `/model` (see `~/.nize-cli-state.json`). |

Precedence order for each setting (highest to lowest): **command-line flag → environment variable → `.env` file → saved state (model only) → built-in default.**

---

## 7. Command-line flags

```bash
python3 aicli.py [flags]
# or, if installed globally:
nize [flags]
```

| Flag | Description |
|---|---|
| `--model <name>` | Use this model for the session instead of the default/saved one. |
| `--base-url <url>` | Override the API base URL (e.g. to point at a different OpenAI-compatible relay). |
| `--api-key <key>` | Pass the API key directly instead of using an environment variable. |
| `--system <text>` | Append extra instructions to the built-in system prompt for this session. |
| `--no-stream` | Parsed but currently a **no-op** — the client always sends non-streaming requests (`"stream": false`) regardless of this flag. Kept for forward-compatibility. |
| `--timeout <seconds>` | Per-request timeout in seconds (converted internally to milliseconds). `0` (default) means no timeout. |
| `-h`, `--help` | Print the script's built-in help text (the module docstring) and exit. |

---

## 8. In-chat commands

Once you're inside the chat, these slash-commands are available:

| Command | What it does |
|---|---|
| `/exit` or `/quit` | Leave the program. |
| `/clear` | Wipes the conversation history (keeps your current model and any `/system` override). |
| `/model` | Lists all available models with numbers; prompts you to pick one by number or (partial) name. |
| `/model <name or number>` | Switches model directly — accepts an exact name, a partial/fuzzy name (as long as it's unambiguous), or its list number. |
| `/system <text>` | Replaces the extra system-prompt instructions for the rest of the session. |
| `/save <file>` | Saves the **last AI reply** to a file: if the reply contains a fenced code block, only that code is saved; otherwise the full reply text is saved. Written relative to the directory you launched Nize from (not the script's own folder). |
| `/export <file>` | Dumps the entire conversation (all messages, as JSON) to a file, same directory rule as `/save`. |
| `/read <file>` | Reads a local file, shows it in a syntax-highlighted panel (first 20,000 characters), and feeds its content into the conversation so the AI can use it as context. |
| `/help` | Prints the full help text (usage, env vars, and this command list). |

Anything you type that isn't one of the commands above is sent to the model as a normal chat message.

---

## 9. Available models

The relay currently exposes the following model names (pick with `/model <number>` or `/model <name>`):

| # | Model |
|---|---|
| 1 | `DeepSeek-V4-Flash` |
| 2 | `DeepSeek-V4-Pro` |
| 3 | `glm-4.7` |
| 4 | `glm-5.1` |
| 5 | `glm-5.2` |
| 6 | `kat-coder-pro-v2` |
| 7 | `Kimi-K2.6` |
| 8 | `MiniMax-M2.7` |
| 9 | `MiniMax-M3` |
| 10 | `Qwen3-Coder-Next-FP8` |
| 11 | `Qwen3.5-397B-A17B` *(default)* |
| 12 | `Qwen3.6-35B-A3B` |
| 13 | `sensenova-6.7-flash-lite` |
| 14 | `sensenova-u1-fast` |
| 15 | `Spark-X2-Flash` |
| 16 | `step-3.5-flash` |
| 17 | `step-3.5-flash-2603` |
| 18 | `step-3.7-flash` |
| 19 | `step-image-edit-2` |
| 20 | `step-router-v1` |
| 21 | `stepaudio-2.5-asr` |
| 22 | `stepaudio-2.5-chat` |
| 23 | `stepaudio-2.5-realtime` |
| 24 | `stepaudio-2.5-tts` |

> This list is hard-coded in `aicli.py` (`AVAILABLE_MODELS`). If the provider adds or renames models, you'll need to edit that list in the script yourself, or simply pass any valid model name directly via `--model` / `/model <exact-name>` even if it isn't in the list.

---

## 10. Agentic tools: shell commands & file saving

This is the most distinctive part of Nize: the AI isn't limited to text — it can ask to run shell commands or write files, but **you're always the one who approves anything risky.**

### 10.1 `run_shell_command`

- The model can request commands like `curl -I`, `dig`, `nslookup`, `whois`, `ping`, `traceroute`, `openssl s_client`, etc., to actually check a live URL/domain/host instead of guessing.
- Every command is displayed in a panel first, along with a one-line "reason" the model gives for running it.
- **Safe, read-only commands run automatically** ("auto-approved · safe").
- **Commands matching a known-dangerous pattern always stop and ask you** to type `y` (yes), `n` (no), or `e` (edit the command before running it).
- The agent loop caps out at **4 steps per turn** — if the model keeps requesting more tools after that, Nize forces it to give a final answer using whatever it already has.
- Command output is captured and truncated (6,000 chars of stdout, 2,000 of stderr) before being shown to you and fed back to the model.
- Each command run has an internal timeout of 25 seconds.

### 10.2 Dangerous-command detection

The following categories of commands are **always** flagged for manual approval, no matter what, even if the model claims it's safe:

| Category | Examples matched |
|---|---|
| Destructive delete | `rm -rf`, `rm --no-preserve-root` |
| Raw disk / filesystem operations | `dd of=...`, `mkfs`, writing to `/dev/sdX` |
| Fork bomb | `:(){ :\|:& };:` |
| Permission/ownership changes | `chmod -R 777`, `chown -R` |
| Privilege escalation | any `sudo` usage |
| System power state | `shutdown`, `reboot`, `halt`, `poweroff` |
| Process killing | `kill -9 1`, `killall` |
| Disk/drive formatting | `format` |
| Destructive SQL | `DROP DATABASE`/`DROP TABLE`, `TRUNCATE` |
| Destructive Git operations | `git push --force`, `git reset --hard` |
| Remote-script execution | `curl \| sh`, `wget \| bash`, etc. |
| System file overwrite | redirecting output into `/etc/...` |
| Firewall/service tampering | `iptables -F`, `systemctl stop/disable/mask ...` |
| Scheduler wipe | `crontab -r` |
| Dynamic code execution | `eval ...` |
| Moving files to root | `mv ... /` |
| Windows forced/silent delete | `del /f`, `erase /q`, etc. |

Anything **not** matching one of these patterns is treated as safe and runs without a prompt — so the model can freely run things like `curl -I https://example.com` or `dig example.com` without interrupting your flow.

### 10.3 `save_file`

- Lets the AI write a finished file (webpage, script, config, etc.) straight to disk at any path — relative, absolute, or using `~`.
- Missing parent folders are created automatically.
- Per the system prompt baked into the app, the AI is instructed to **always ask you to confirm the save location** in the conversation before calling this tool — it should never call it speculatively without your go-ahead.
- Writing is **blocked outright** (regardless of confirmation) for a fixed list of sensitive system paths: `/etc`, `/bin`, `/sbin`, `/usr/bin`, `/usr/sbin`, `/boot`, `/sys`, `/proc`, `/lib`, `/lib64`, `/dev`, `/var/lib`, `/root`.

---

## 11. Usage examples

**Start a normal chat session:**

```bash
nize
```

**Start with a specific model and a custom system instruction:**

```bash
python3 aicli.py --model glm-5.2 --system "You are a terse, no-nonsense assistant."
```

**Point the client at a different OpenAI-compatible endpoint entirely:**

```bash
python3 aicli.py --base-url https://some-other-relay.example.com/v1 --api-key sk-xxxxx
```

**Inside a chat session:**

```
you › /model
        (shows the numbered model list)
you › /model 5
        (switches to glm-5.2)
you › Check if example.com is up and show me its TLS cert info
        (the AI proposes a curl -I and an openssl s_client command; safe ones run
         automatically, then it summarizes the findings for you)
you › /save result.txt
        (saves the last reply's code block, or full text, into your current folder)
you › /export session.json
        (dumps the whole conversation so far to session.json)
you › /exit
```

---

## 12. Running on Android (Termux)

Both `aicli.py` and `install.sh` are written to work in [Termux](https://termux.dev/):

1. Install Termux (from F-Droid is recommended over the Play Store version, which is outdated).
2. Inside Termux:
   ```bash
   pkg update && pkg upgrade
   pkg install python
   pip install rich requests
   ```
3. Copy or transfer `aicli.py`, `install.sh`, and `requirements.txt` into Termux's storage.
4. Set your API key (see [Step 5](#step-5--configure-the-api-key)).
5. Run `bash install.sh` — it detects Termux automatically (via the `$PREFIX` variable) and installs `nize` into `$PREFIX/bin` instead of `~/.local/bin`.
6. Run `nize` from anywhere in Termux.

---

## 13. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `No API key found.` on startup | `AICLI_API_KEY` isn't set and no valid `--api-key` was passed. Double-check Step 5, and remember the `.env` file location rule if you're using one. |
| `HTTP 401` / authorization errors | Your API key is invalid, expired, or wasn't copied fully. Regenerate a token on api.iamhc.cn's Token Management page. |
| Request hangs or times out | Try again, or pass a longer timeout: `--timeout 60`. Also check your internet connection and whether a firewall/VPN is blocking the domain. |
| `✖ Request failed: ...` with connection errors | Nize already retries twice automatically with backoff before showing this. If it persists, test connectivity manually: `curl -I https://api.iamhc.cn/v1`. |
| A model name you pick with `/model` isn't recognized | It must match (fully or as an unambiguous partial match) an entry in `AVAILABLE_MODELS`, or you can pass any exact model name string the provider actually supports even if it's not pre-listed. |
| `.env` values seem to be ignored | Remember: the script only loads `.env` from *its own* folder — not your current directory — and only fills in variables that aren't already set as real environment variables. |
| `/save` or `/export` write to an unexpected place | Both always write relative to the directory you were in **when you launched Nize**, not the script's install folder. |
| Commands never ask for approval | That's expected for anything not matching the dangerous-pattern list — those are treated as safe/read-only and run automatically. Only flagged commands (see the table in [Section 10.2](#102-dangerous-command-detection)) pause for your input. |

---

## 14. Uninstalling

If you installed the global command with `install.sh`:

```bash
rm "$(command -v nize)"
```

Then remove the `export PATH=...` line the installer added to your `~/.bashrc` or `~/.zshrc`, if you no longer need it (only necessary if you don't use that directory for anything else).

If you only ever ran it with `python3 aicli.py`, just delete the project folder — there's nothing else installed system-wide, aside from the `rich`/`requests` pip packages and the small state file at `~/.nize-cli-state.json`, which you can also remove:

```bash
rm ~/.nize-cli-state.json
```

---

## 15. Security & privacy notes

- **Your API key is sensitive.** It's read from an environment variable or `.env` file and sent as a Bearer token with every request — never commit it to version control or share it publicly.
- **Everything you type, plus tool outputs (command results, file contents you `/read`), is sent to the configured API endpoint** as part of the conversation. Don't paste secrets, credentials, or sensitive personal data into the chat if you don't fully trust the provider handling that traffic.
- **Shell command execution is real and local** — commands run with your own user's permissions on your own machine via Python's `subprocess`. The dangerous-pattern list and approval prompts are a safety net, not a sandbox; they catch known-risky patterns but can't guarantee every conceivable harmful command is caught. Review anything you're not sure about before approving it, and don't run this tool as `root`/an administrator account.
- **`save_file` can create real files anywhere you confirm** outside of the explicitly blocked system paths — treat file-save confirmations with the same care you'd give any other write operation.
- The conversation history is kept only in memory for the duration of the process (aside from what you explicitly `/export` or `/save`); nothing is persisted automatically except your last-selected model name.

---

## 16. About the API provider (api.iamhc.cn)

`api.iamhc.cn` is a **third-party** API aggregation/relay service (built on the open-source "New API" project) that exposes multiple large language models behind one OpenAI-compatible endpoint. It is **not** operated by Anthropic, OpenAI, or any of the original model providers, and it is not affiliated with this Nize CLI project's documentation beyond being the default endpoint configured in `aicli.py`.

A few practical points worth knowing before relying on it:

- It offers a **free tier** with limited request quotas and rate limits, alongside **paid subscription tiers** for higher throughput/priority access.
- Available models, pricing, rate limits, and UI details are controlled entirely by that third party and **can change at any time** without notice.
- As with any third-party relay, review its **Terms of Service and Privacy Policy** yourself before sending anything sensitive through it, and keep in mind that reliability/uptime is outside the control of this project.
- If you'd rather use a different OpenAI-compatible provider, just change `AICLI_BASE_URL` (and `AICLI_API_KEY`) to point at that provider instead — the client doesn't hard-depend on this specific relay.

---

## 17. License

This repository is licensed under the **MIT License**.

In short: you're free to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of this software, for personal or commercial purposes, as long as the original copyright notice and license text are included in any copy or substantial portion of the software. The software is provided **"as is"**, without warranty of any kind — the authors aren't liable for any claim, damages, or other liability arising from its use.

A full `LICENSE` file with the standard MIT text is included in this repository — see [`LICENSE`](./LICENSE) for the complete terms.

---

## 18. Credits

Built as a single-file terminal AI client ("Nize") wrapping an OpenAI-compatible chat-completions API, with a `rich`-powered UI and an approval-gated shell/file-tool agent loop.

Released under the MIT License.
