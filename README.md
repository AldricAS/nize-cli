# Nize CLI

Nize is a terminal-based AI chat client that connects to the **api.iamhc.cn** relay (OpenAI-compatible). No external dependencies — it just uses Node.js's built-in `fetch` and `readline`.

Besides regular chat, Nize can run **real shell commands** (curl, dig, whois, openssl, ping, etc.) to check things like a URL or domain directly — but every command must be approved by you before it runs.

## ✨ Features

- AI chat right from the terminal, no extra dependencies
- Switch AI models anytime with the `/model` command
- Tool calling: the AI can ask permission to run read-only shell commands to fetch real data (headers, DNS, TLS certificates, etc.)
- Save the AI's reply (code) straight to a file with `/save`
- Export the whole conversation to JSON with `/export`
- Change the system prompt mid-session with `/system`
- Your model choice is saved automatically for the next session

## 📦 Installation

```bash
git clone https://github.com/AldricAS/nize-cli.git
cd nize-cli
```

No `npm install` needed — Nize has zero external dependencies, just Node.js 18+ (since it relies on the built-in `fetch`).

## ⚙️ Configuration

Create a `.env` file in the same folder as `aicli.js`:

```env
AICLI_API_KEY=your_api_key_from_iamhc
AICLI_BASE_URL=https://api.iamhc.cn/v1
AICLI_MODEL=Qwen3.5-397B-A17B
```

Details:
- **AICLI_API_KEY** — required. Get your API key from your account at [iamhc](https://api.iamhc.cn).
- **AICLI_BASE_URL** — can be left as is, defaults to `https://api.iamhc.cn/v1`.
- **AICLI_MODEL** — the default model used when chat starts. Can be changed anytime with `/model` inside the chat. Example available models: `DeepSeek-V4-Pro`, `glm-5.2`, `Kimi-K2.6`, `MiniMax-M3`, `Qwen3-Coder-Next-FP8`, and more (see the full list by typing `/model` while chatting).


## 🚀 Running

```bash
node aicli.js
```

Or directly with extra options:

```bash
node aicli.js --model glm-5.2 --system "Answer briefly and directly."
```

## 🌐 Call it with just `nize` (global, via `npm link`)

So you don't have to type `node aicli.js` every time, you can register Nize as a global command and just type `nize` from any folder.

1. Make sure `aicli.js` is executable (Linux/macOS only):

   ```bash
   chmod +x aicli.js
   ```

2. From inside this project folder, run:

   ```bash
   npm link
   ```

   This reads the `bin` field in `package.json` (`"nize": "./aicli.js"`) and creates a global symlink, so the `nize` command becomes available in your PATH.

3. Now from any folder, just run:

   ```bash
   nize
   ```

   or with extra options as usual:

   ```bash
   nize --model glm-5.2 --system "Answer briefly and directly."
   ```

> Note: the `.env` file is still read from the folder where the original `aicli.js` lives (not the folder you run `nize` from), so keep `.env` in this project folder.

To unlink the global command later:

```bash
npm unlink -g nize-cli
```

## 💬 In-chat commands

| Command | Function |
|---|---|
| `/exit` or `/quit` | Leave the chat |
| `/clear` | Wipe the conversation history |
| `/model` | List available models and pick one interactively |
| `/model <name>` | Switch model directly (accepts a number or partial name) |
| `/system <text>` | Change the system prompt mid-session |
| `/save <file>` | Save the last AI reply's code block to a file |
| `/export <file>` | Save the whole conversation as JSON |
| `/help` | Show this list of commands |

## 🛠️ Terminal access by the AI

Nize can ask permission to run real (read-only) shell commands to fetch live data — for example checking a domain's DNS, HTTP headers, or TLS certificate — but **every command is shown to you first**, and only runs after you approve it with `y` (yes), `n` (no), or `e` (edit the command before running).

## 📄 License

This project is licensed under [MIT](LICENSE) — free to use, modify, and redistribute, as long as the copyright notice is kept.
