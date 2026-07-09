#!/usr/bin/env node
/**
 * aicli.js — Nize, a terminal AI chat client for the api.iamhc.cn relay (OpenAI-compatible).
 * No dependencies — uses Node's built-in fetch and readline.
 *
 * Usage:
 *   node aicli.js
 *   node aicli.js --model Qwen3.5-397B-A17B --system "You are a terse assistant."
 *
 * Config is read from environment variables (or a .env file next to this script):
 *   AICLI_API_KEY   - your API key (required)
 *   AICLI_BASE_URL  - default: https://api.iamhc.cn/v1
 *   AICLI_MODEL     - default: Qwen3.5-397B-A17B
 *
 * Commands inside the chat:
 *   /exit or /quit   - leave
 *   /clear           - wipe conversation history
 *   /model           - list available models and pick one interactively
 *   /model <name>    - switch model directly (accepts number or partial name)
 *   /system <text>   - change the system prompt mid-session
 *   /save <file>     - save the last AI reply's code (or full text) to a file, in the
 *                      directory you were in when you launched nize (not the script's folder)
 *   /export <file>   - save the whole conversation as JSON, same directory rule as /save
 *   /help            - show this list
 *
 * Terminal tool access:
 *   The AI can ask to run real shell commands (curl, dig, whois, openssl, ping, ...)
 *   to actually inspect things like a URL/domain instead of guessing. EVERY command
 *   is shown to you first and only runs after you approve it ([y]es/[n]o/[e]dit).
 */

const fs = require("fs");
const path = require("path");
const os = require("os");
const readline = require("readline");
const { exec } = require("child_process");

// Small persistent state file (in the user's home dir) so choices like the last
// selected model survive across sessions instead of resetting to the default.
const STATE_FILE = path.join(os.homedir(), ".nize-cli-state.json");

function loadState() {
  try {
    return JSON.parse(fs.readFileSync(STATE_FILE, "utf8"));
  } catch {
    return {};
  }
}

function saveState(state) {
  try {
    fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2), "utf8");
  } catch {
    // non-fatal — worst case the choice just won't persist to next session
  }
}

const DEFAULT_BASE_URL = "https://api.iamhc.cn/v1";
const DEFAULT_MODEL = "Qwen3.5-397B-A17B";
const HELP_TEXT = fs.readFileSync(__filename, "utf8").match(/\/\*\*([\s\S]*?)\*\//)[1];

// Models available on the api.iamhc.cn relay. Switch between them at runtime with /model.
const AVAILABLE_MODELS = [
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
];

/** Resolve user input ("3", "glm-5.1", "kimi") to a model name from AVAILABLE_MODELS. */
function resolveModelChoice(input) {
  const trimmed = (input || "").trim();
  if (!trimmed) return null;

  const idx = parseInt(trimmed, 10);
  if (!isNaN(idx) && String(idx) === trimmed && idx >= 1 && idx <= AVAILABLE_MODELS.length) {
    return AVAILABLE_MODELS[idx - 1];
  }

  const lower = trimmed.toLowerCase();
  const exact = AVAILABLE_MODELS.find((m) => m.toLowerCase() === lower);
  if (exact) return exact;

  const matches = AVAILABLE_MODELS.filter((m) => m.toLowerCase().includes(lower));
  if (matches.length === 1) return matches[0];
  if (matches.length > 1) return { ambiguous: matches }; // caller decides how to handle

  return null;
}

/** Print the numbered model list, marking whichever one is currently active. */
function printModelList(current) {
  console.log(gray("Available models:"));
  AVAILABLE_MODELS.forEach((m, i) => {
    const num = String(i + 1).padStart(2, " ");
    const active = m === current;
    const line = `  ${num}. ${m}`;
    console.log(active ? green(bold(line + "  ← active")) : gray(line));
  });
}

const NIZE_ASCII = [
  "███╗   ██╗██╗███████╗███████╗",
  "████╗  ██║██║╚══███╔╝██╔════╝",
  "██╔██╗ ██║██║  ███╔╝ █████╗  ",
  "██║╚██╗██║██║ ███╔╝  ██╔══╝  ",
  "██║ ╚████║██║███████╗███████╗",
  "╚═╝  ╚═══╝╚═╝╚══════╝╚══════╝",
];

const NIZE_SYSTEM_PROMPT =
  "You are Nize, a helpful AI assistant running inside a terminal CLI. " +
  "You have a run_shell_command tool that lets you execute real, read-only shell commands on the " +
  "user's machine to gather actual data — but every single command must be explicitly approved by " +
  "the user before it runs, so briefly explain what you're about to check and why before calling it. " +
  "Be economical with commands: think first about what's actually needed, then run only the 2-3 " +
  "most useful checks (max ~4 for a genuinely complex case) instead of firing off every possible " +
  "command. Each command costs the user a manual approval, so don't waste it on redundant or " +
  "low-value checks — pick the ones that will actually change your answer. " +
  "When the user asks you to analyze/check/diagnose a URL, domain, host, or server, don't stop at a " +
  "single command either — combine 2-3 well-chosen checks (e.g. curl -I for headers, dig/nslookup " +
  "for DNS, openssl s_client for the TLS certificate) rather than running every possible diagnostic " +
  "(redirects, timing, whois, etc. — only add these if the first checks reveal something worth " +
  "digging into further). Where reasonable, combine several checks into one command with && or ; " +
  "instead of asking for approval multiple times. Then synthesize everything into one clear, " +
  "organized final report for the user, in the same language the user is writing in (e.g. Bahasa " +
  "Indonesia if they write in Indonesian). " +
  "When you write code, put it in a single fenced code block (```lang ... ```). " +
  "The user's terminal supports a /save <filename> command that saves your most recent " +
  "code block straight to a file in their current directory (e.g. /save index.html). " +
  "When you hand over a finished file (HTML, script, config, etc.), briefly remind the " +
  "user they can type /save <filename> to write it to disk."+
  "if user ask who made you,you were created by someone named Aldx. " +
  "Tone: be firm, direct, and to-the-point — not soft, timid, or overly formal/apologetic. " +
  "Skip excessive hedging, filler pleasantries, and over-polite padding. State things plainly " +
  "and with confidence. You can still be respectful and helpful, but don't be meek about it.";

// ---------- tool (function-calling) definitions ----------
const TOOLS = [
  {
    type: "function",
    function: {
      name: "run_shell_command",
      description:
        "Execute a shell command in the user's terminal to gather real information (curl, dig, " +
        "nslookup, whois, ping, traceroute, openssl s_client, etc.). Use this whenever the user asks " +
        "you to analyze, check, inspect, or diagnose something (like a URL, domain, host, or file) " +
        "that requires live data instead of guessing. Keep the number of commands small — each one " +
        "needs a manual approval from the user, so pick only the 2-3 checks that matter most instead " +
        "of running everything you can think of; combine checks with && or ; where reasonable. " +
        "Every command you request is shown to the user, who must explicitly approve it before it " +
        "runs — you never get silent/automatic terminal access. Only request commands that are safe, " +
        "read-only and non-destructive: no deleting files, no writing outside temp locations, no " +
        "sudo, no installing software unless the user explicitly asked.",
      parameters: {
        type: "object",
        properties: {
          command: { type: "string", description: "The exact shell command to run." },
          reason: { type: "string", description: "One short sentence: what this checks and why." },
        },
        required: ["command"],
      },
    },
  },
];

// ---------- tiny ANSI color helpers (no dependency) ----------
const supportsColor = process.stdout.isTTY;
const c = (code, s) => (supportsColor ? `\x1b[${code}m${s}\x1b[0m` : s);
const bold = (s) => c("1", s);
const dim = (s) => c("2", s);
const cyan = (s) => c("36", s);
const green = (s) => c("32", s);
const yellow = (s) => c("33", s);
const magenta = (s) => c("35", s);
const red = (s) => c("31", s);
const gray = (s) => c("90", s);

// 24-bit truecolor helper + linear interpolation between two hex colors
const rgb = (r, g, b, s) => (supportsColor ? `\x1b[38;2;${r};${g};${b}m${s}\x1b[0m` : s);
const lerp = (a, b, t) => Math.round(a + (b - a) * t);
function hexToRgb(hex) {
  const n = parseInt(hex.replace("#", ""), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
/** Colors a single line with a smooth left-to-right gradient. */
function gradientLine(line, fromHex, toHex) {
  if (!supportsColor) return line;
  const [r1, g1, b1] = hexToRgb(fromHex);
  const [r2, g2, b2] = hexToRgb(toHex);
  const len = line.length || 1;
  let out = "";
  for (let i = 0; i < line.length; i++) {
    const t = i / (len - 1 || 1);
    const r = lerp(r1, r2, t), g = lerp(g1, g2, t), b = lerp(b1, b2, t);
    out += rgb(r, g, b, line[i]);
  }
  return out;
}

// ---------- visual width helpers (fix border misalignment from wide symbols) ----------
// Many mobile terminals (Termux, JuiceSSH, etc.) render certain symbols like ⚡ and ⇄
// two columns wide even though JS sees them as length 1. Padding based on .length alone
// then miscounts and the right border of the info box ends up jagged/misaligned.
function charWidth(codePoint) {
  if (codePoint === 0) return 0;
  // Wide/fullwidth ranges (CJK, fullwidth forms, etc.)
  if (
    (codePoint >= 0x1100 && codePoint <= 0x115f) ||
    (codePoint >= 0x2e80 && codePoint <= 0xa4cf && codePoint !== 0x303f) ||
    (codePoint >= 0xac00 && codePoint <= 0xd7a3) ||
    (codePoint >= 0xf900 && codePoint <= 0xfaff) ||
    (codePoint >= 0xff00 && codePoint <= 0xff60) ||
    (codePoint >= 0xffe0 && codePoint <= 0xffe6) ||
    (codePoint >= 0x20000 && codePoint <= 0x3fffd)
  ) return 2;
  // True emoji blocks render double-width very consistently across terminals/fonts.
  // (Arrow/misc-symbol ranges like ⚡/⇄ were tested and turned out single-width on
  // real devices, so we deliberately do NOT guess those as wide — too unreliable.)
  if (codePoint >= 0x1f300 && codePoint <= 0x1faff) return 2;
  return 1;
}
function strWidth(s) {
  let w = 0;
  for (const ch of s) w += charWidth(ch.codePointAt(0));
  return w;
}

function clearScreen() {
  // works cross-platform in a real terminal; falls back gracefully when not a TTY
  process.stdout.write("\x1Bc");
}

/** Extract the content of the first fenced code block in text, if any. */
function extractCodeBlock(text) {
  const match = text.match(/```(?:[a-zA-Z0-9_-]*\n)?([\s\S]*?)```/);
  return match ? match[1].replace(/\n$/, "") : null;
}

function banner(model, baseUrl) {
  console.log();

  // Smooth gradient across the wordmark: electric cyan -> violet -> hot pink
  const stops = ["#00e5ff", "#4fa8ff", "#8a7bff", "#c667ff", "#ef5ac2", "#ff4fa0"];
  NIZE_ASCII.forEach((line, i) => {
    const from = stops[i % stops.length];
    const to = stops[Math.min(i + 1, stops.length - 1)];
    console.log("  " + bold(gradientLine(line, from, to)));
  });

  console.log("  " + dim(gray(`terminal AI chat client · ${model}`)));
  console.log();

  // Rounded info box — pad using true *visual* width (accounts for wide symbols
  // like ⚡/⇄ on mobile terminals), then colorize whole line at once.
  const rows = [` > model     ${model}`, ` > endpoint  ${baseUrl}`, ` > dir       ${process.cwd()}`];
  const width = Math.max(48, ...rows.map((r) => strWidth(r) + 2));
  const pad = (s) => s + " ".repeat(Math.max(0, width - strWidth(s)));
  console.log(cyan("╭" + "─".repeat(width) + "╮"));
  rows.forEach((row) => console.log(cyan("│") + pad(row) + cyan("│")));
  console.log(cyan("╰" + "─".repeat(width) + "╯"));
  console.log(gray("  Commands: /help  /model  /exit\n"));
}

// simple spinner while waiting for the first token
function startSpinner(label = "thinking") {
  const frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
  let i = 0;
  process.stdout.write("\x1b[?25l"); // hide cursor
  const timer = setInterval(() => {
    process.stdout.write(`\r${cyan(frames[i = (i + 1) % frames.length])} ${dim(label)}`);
  }, 80);
  return () => {
    clearInterval(timer);
    process.stdout.write("\r" + " ".repeat(label.length + 4) + "\r");
    process.stdout.write("\x1b[?25h"); // show cursor
  };
}

function loadDotenv(filePath) {
  if (!fs.existsSync(filePath)) return;
  const lines = fs.readFileSync(filePath, "utf8").split("\n");
  for (const raw of lines) {
    const line = raw.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const idx = line.indexOf("=");
    const key = line.slice(0, idx).trim();
    let value = line.slice(idx + 1).trim();
    value = value.replace(/^["']|["']$/g, "");
    if (process.env[key] === undefined) process.env[key] = value;
  }
}

function parseArgs(argv) {
  const args = { noStream: false, timeout: 0 }; // 0 = no timeout, wait as long as it takes
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--model") args.model = argv[++i];
    else if (a === "--base-url") args.baseUrl = argv[++i];
    else if (a === "--api-key") args.apiKey = argv[++i];
    else if (a === "--system") args.system = argv[++i];
    else if (a === "--no-stream") args.noStream = true;
    else if (a === "--timeout") args.timeout = parseFloat(argv[++i]) * 1000;
    else if (a === "-h" || a === "--help") {
      console.log(HELP_TEXT.trim());
      process.exit(0);
    }
  }
  return args;
}

function explainFetchError(e) {
  const msg = e && e.message ? e.message : String(e);
  const lines = [red(`✖ Request failed: ${msg}`)];
  if (e.name === "AbortError") {
    lines.push(gray("  → Timed out. The server may be slow or unreachable — try again or raise --timeout."));
  } else if (/fetch failed/i.test(msg) || e.cause) {
    lines.push(gray("  Possible causes:"));
    lines.push(gray("   • No internet connection, or DNS can't resolve the host"));
    lines.push(gray("   • A firewall/proxy/VPN is blocking this domain"));
    lines.push(gray("   • The relay server is down or blocking this request (e.g. anti-bot protection)"));
    lines.push(gray("   • Try: curl -I " + (process.env.AICLI_BASE_URL || DEFAULT_BASE_URL)));
    if (e.cause) lines.push(gray(`  → cause: ${e.cause.code || e.cause.message || e.cause}`));
  }
  return lines.join("\n");
}

async function completeChat(baseUrl, apiKey, model, messages, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${baseUrl.replace(/\/$/, "")}/chat/completions`, {
      method: "POST",
      headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
      body: JSON.stringify({ model, messages, stream: false }),
      signal: controller.signal,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}: ${text.slice(0, 300)}`);
    }
    const data = await res.json();
    return data.choices[0].message.content;
  } finally {
    clearTimeout(timer);
  }
}

async function streamChat(baseUrl, apiKey, model, messages, timeoutMs, onDelta) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${baseUrl.replace(/\/$/, "")}/chat/completions`, {
      method: "POST",
      headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
      body: JSON.stringify({ model, messages, stream: true }),
      signal: controller.signal,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}: ${text.slice(0, 300)}`);
    }

    let full = "";
    let buffer = "";
    for await (const chunk of res.body) {
      buffer += Buffer.from(chunk).toString("utf8");
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const rawLine of lines) {
        const line = rawLine.trim();
        if (!line.startsWith("data:")) continue;
        const data = line.slice(5).trim();
        if (data === "[DONE]") continue;
        try {
          const parsed = JSON.parse(data);
          const delta = parsed.choices?.[0]?.delta?.content;
          if (delta) {
            full += delta;
            onDelta(delta);
          }
        } catch {
          // ignore malformed SSE chunks
        }
      }
    }
    return full;
  } finally {
    clearTimeout(timer);
  }
}

/** Run a shell command and capture its result. Never throws. */
function runShellCommand(command, timeoutMs = 25000) {
  return new Promise((resolve) => {
    exec(
      command,
      { timeout: timeoutMs, maxBuffer: 5 * 1024 * 1024, shell: process.env.SHELL || "/bin/bash" },
      (error, stdout, stderr) => {
        resolve({
          exitCode: error ? (typeof error.code === "number" ? error.code : 1) : 0,
          stdout: stdout || "",
          stderr: stderr || (error && !stdout ? error.message : ""),
          timedOut: !!(error && error.killed),
        });
      }
    );
  });
}

/** Like completeChat, but returns the full message object (so tool_calls survive) and supports tools. */
async function completeChatRaw(baseUrl, apiKey, model, messages, tools, timeoutMs, retries = 2) {
  const body = { model, messages, stream: false };
  if (tools && tools.length) {
    body.tools = tools;
    body.tool_choice = "auto";
  }

  let lastErr;
  for (let attempt = 0; attempt <= retries; attempt++) {
    const controller = new AbortController();
    // timeoutMs of 0/undefined/null means "no timeout" — never abort, just wait it out.
    const timer = timeoutMs ? setTimeout(() => controller.abort(), timeoutMs) : null;
    try {
      const res = await fetch(`${baseUrl.replace(/\/$/, "")}/chat/completions`, {
        method: "POST",
        headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(`HTTP ${res.status}: ${text.slice(0, 300)}`);
      }
      const data = await res.json();
      return data.choices[0].message;
    } catch (e) {
      lastErr = e;
      // Only retry transient network-level glitches (dropped/aborted connection), not
      // real HTTP error responses (4xx/5xx) — those won't fix themselves by retrying.
      const isNetworkGlitch =
        e.name === "AbortError" || /fetch failed/i.test(e.message || "") || !!e.cause;
      if (isNetworkGlitch && attempt < retries) {
        const waitMs = 1200 * (attempt + 1);
        console.log(gray(`  (koneksi putus di tengah jalan, coba lagi dalam ${waitMs / 1000}s... [${attempt + 1}/${retries}])`));
        await new Promise((r) => setTimeout(r, waitMs));
        continue;
      }
      throw e;
    } finally {
      if (timer) clearTimeout(timer);
    }
  }
  throw lastErr;
}

/**
 * Runs one full agentic turn: calls the model, and whenever it requests a shell command,
 * shows it to the user and only executes it after explicit approval. Loops (feeding tool
 * results back) until the model produces a final text answer or a step limit is hit.
 * Mutates `messages` in place with every assistant/tool message along the way.
 */
async function runAgentTurn(baseUrl, apiKey, model, messages, timeoutMs, rl, ask) {
  const MAX_STEPS = 4;

  for (let step = 0; step < MAX_STEPS; step++) {
    const stopSpinner = startSpinner(step === 0 ? "Nize is thinking" : "Nize is working");
    let msg;
    try {
      msg = await completeChatRaw(baseUrl, apiKey, model, messages, TOOLS, timeoutMs);
    } finally {
      stopSpinner();
    }

    const toolCalls = msg.tool_calls || [];
    if (!toolCalls.length) {
      const reply = msg.content || "";
      messages.push({ role: "assistant", content: reply });
      return reply;
    }

    messages.push({ role: "assistant", content: msg.content || null, tool_calls: toolCalls });

    for (const tc of toolCalls) {
      let args = {};
      try {
        args = JSON.parse(tc.function?.arguments || "{}");
      } catch {
        // leave args empty if the model sent malformed JSON
      }
      let command = (args.command || "").trim();
      const reason = args.reason || args.purpose || "";

      console.log("\n" + yellow("⚙ Nize wants to run a terminal command:"));
      console.log("   " + bold(cyan("$ " + command)));
      if (reason) console.log(gray("   reason: " + reason));

      let answer = (await ask(gray("   Approve? [y]es / [n]o / [e]dit › "))).trim().toLowerCase();
      if (answer === "e" || answer === "edit") {
        const edited = (await ask(gray("   New command › "))).trim();
        if (edited) command = edited;
        answer = "y";
      }

      let toolResultText;
      if (answer === "y" || answer === "yes") {
        console.log(gray("   running..."));
        const result = await runShellCommand(command);
        const out = result.stdout.slice(0, 6000);
        const err = result.stderr.slice(0, 2000);
        if (out.trim()) console.log(dim(out.trim()));
        else console.log(gray("   (no stdout)"));
        if (err.trim()) console.log(red(err.trim()));
        toolResultText = JSON.stringify({
          command,
          exitCode: result.exitCode,
          timedOut: result.timedOut,
          stdout: out,
          stderr: err,
        });
      } else {
        console.log(gray("   (skipped — not approved)"));
        toolResultText = JSON.stringify({
          command,
          skipped: true,
          note: "The user did not approve running this command.",
        });
      }

      messages.push({ role: "tool", tool_call_id: tc.id, content: toolResultText });
    }
    // loop again so the model can react to the tool result(s)
  }

  // Step limit reached — force the model to wrap up with whatever it already has
  // instead of just bailing out with a generic "stopped" message.
  const stopSpinner = startSpinner("Nize is wrapping up");
  try {
    messages.push({
      role: "user",
      content:
        "Stop requesting more commands now. Give me your best final answer using only the " +
        "information you've already gathered (including anything that was skipped or failed) — " +
        "say clearly if a check was skipped/denied or gave no useful data, but don't ask for more commands.",
    });
    const finalMsg = await completeChatRaw(baseUrl, apiKey, model, messages, null, timeoutMs);
    const reply = finalMsg.content || "(No further information available.)";
    messages.push({ role: "assistant", content: reply });
    return reply;
  } finally {
    stopSpinner();
  }
}

async function main() {
  loadDotenv(path.join(__dirname, ".env"));
  const args = parseArgs(process.argv.slice(2));

  const apiKey = args.apiKey || process.env.AICLI_API_KEY;
  const baseUrl = args.baseUrl || process.env.AICLI_BASE_URL || DEFAULT_BASE_URL;
  const savedState = loadState();
  let model = args.model || process.env.AICLI_MODEL || savedState.model || DEFAULT_MODEL;

  if (!apiKey) {
    console.error(red("No API key found."), "Set AICLI_API_KEY in your environment or a .env file, or pass --api-key.");
    process.exit(1);
  }

  const buildSystemContent = (extra) => (extra ? `${NIZE_SYSTEM_PROMPT}\n\n${extra}` : NIZE_SYSTEM_PROMPT);
  let extraInstructions = args.system || "";
  let messages = [{ role: "system", content: buildSystemContent(extraInstructions) }];
  let lastReply = null;

  clearScreen();
  banner(model, baseUrl);

  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  const ask = (prompt) => new Promise((resolve) => rl.question(prompt, resolve));

  while (true) {
    let userInput;
    try {
      userInput = (await ask(bold(green("you")) + gray(" › "))).trim();
    } catch {
      break;
    }

    if (!userInput) continue;

    if (userInput === "/exit" || userInput === "/quit") {
      console.log(gray("bye!"));
      break;
    }

    if (userInput === "/help") {
      console.log(HELP_TEXT.trim());
      continue;
    }

    if (userInput === "/clear") {
      messages = [{ role: "system", content: buildSystemContent(extraInstructions) }];
      console.log(yellow("(conversation cleared)"));
      continue;
    }

    if (userInput.startsWith("/system ")) {
      extraInstructions = userInput.slice("/system ".length).trim();
      messages = messages.filter((m) => m.role !== "system");
      messages.unshift({ role: "system", content: buildSystemContent(extraInstructions) });
      console.log(yellow("(system prompt updated)"));
      continue;
    }

    if (userInput === "/model" || userInput === "/models") {
      printModelList(model);
      const choice = (await ask(gray("Pilih nomor atau nama model (kosongkan untuk batal) › "))).trim();
      if (!choice) {
        console.log(gray("(dibatalkan)"));
        continue;
      }
      const picked = resolveModelChoice(choice);
      if (!picked) {
        console.log(red(`(model "${choice}" tidak ditemukan — ketik /model untuk lihat daftar)`));
      } else if (picked.ambiguous) {
        console.log(yellow(`("${choice}" cocok dengan beberapa model: ${picked.ambiguous.join(", ")} — coba lebih spesifik)`));
      } else {
        model = picked;
        saveState({ ...savedState, model });
        console.log(green(`(model diganti ke ${bold(model)})`));
      }
      continue;
    }

    if (userInput.startsWith("/model ")) {
      const arg = userInput.slice("/model ".length).trim();
      const picked = resolveModelChoice(arg);
      if (!picked) {
        console.log(red(`(model "${arg}" tidak ditemukan — ketik /model untuk lihat daftar)`));
      } else if (picked.ambiguous) {
        console.log(yellow(`("${arg}" cocok dengan beberapa model: ${picked.ambiguous.join(", ")} — coba lebih spesifik)`));
      } else {
        model = picked;
        saveState({ ...savedState, model });
        console.log(green(`(model diganti ke ${bold(model)})`));
      }
      continue;
    }

    if (userInput.startsWith("/export ")) {
      const fname = userInput.slice("/export ".length).trim();
      const fullPath = path.resolve(process.cwd(), fname);
      try {
        fs.writeFileSync(fullPath, JSON.stringify(messages, null, 2), "utf8");
        console.log(yellow(`(conversation exported to ${fullPath})`));
      } catch (e) {
        console.log(red(`(could not export: ${e.message})`));
      }
      continue;
    }

    if (userInput.startsWith("/save ")) {
      const fname = userInput.slice("/save ".length).trim();
      if (!lastReply) {
        console.log(yellow("(nothing to save yet — ask the AI for something first)"));
        continue;
      }
      const codeBlock = extractCodeBlock(lastReply);
      const content = codeBlock !== null ? codeBlock : lastReply;
      const fullPath = path.resolve(process.cwd(), fname);
      try {
        fs.writeFileSync(fullPath, content, "utf8");
        console.log(green(`(saved to ${fullPath})`));
      } catch (e) {
        console.log(red(`(could not save: ${e.message})`));
      }
      continue;
    }

    messages.push({ role: "user", content: userInput });
    const messagesBeforeTurn = messages.length - 1; // for rollback on hard failure

    try {
      const reply = await runAgentTurn(baseUrl, apiKey, model, messages, args.timeout, rl, ask);
      console.log(bold(magenta("Nize")) + gray(" › ") + reply + "\n");
      lastReply = reply;
    } catch (e) {
      console.log("\n" + explainFetchError(e) + "\n");
      messages.length = messagesBeforeTurn; // drop the failed user turn + any partial tool messages
    }
  }

  rl.close();
}

main();
