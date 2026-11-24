// Service worker: connects to the local relay service and runs primitive commands on the tab it opened.
const DEFAULT_PORT = 8765;
const BADGE = "AUTO";
let ws = null;
let trusted = false;
let drivenTab = null;

const encoder = new TextEncoder();

async function settings() {
  return chrome.storage.local.get({ port: DEFAULT_PORT, token: "", stopped: false });
}

async function hmac(token, message) {
  const key = await crypto.subtle.importKey("raw", encoder.encode(token), { name: "HMAC", hash: "SHA-256" },
    false, ["sign"]);
  const signature = await crypto.subtle.sign("HMAC", key, encoder.encode(message));
  return [...new Uint8Array(signature)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function randomHex(bytes) {
  return [...crypto.getRandomValues(new Uint8Array(bytes))].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function connect() {
  if (ws) return;
  const { port, token } = await settings();
  if (!token) return;
  const socket = new WebSocket(`ws://127.0.0.1:${port}/`);
  ws = socket;
  trusted = false;
  const nonce = randomHex(16);
  socket.onopen = async () => {
    socket.send(JSON.stringify({ type: "hello", nonce, proof: await hmac(token, `client:${nonce}`) }));
  };
  socket.onmessage = async (event) => {
    const message = JSON.parse(event.data);
    if (!trusted) {
      // Obey only a service that proves it knows the pairing token.
      if (message.type === "welcome" && message.proof === await hmac(token, `server:${nonce}`)) {
        trusted = true;
      } else {
        socket.close();
      }
      return;
    }
    if (message.cmd) {
      socket.send(JSON.stringify(await handle(message)));
    }
  };
  socket.onclose = () => {
    if (ws === socket) {
      ws = null;
      trusted = false;
      setTimeout(connect, 3000);
    }
  };
}

function reconnect() {
  const old = ws;
  ws = null;
  trusted = false;
  if (old) old.close();
  connect();
}

setInterval(() => {
  if (ws && trusted) ws.send(JSON.stringify({ type: "ping" }));
}, 20000);
chrome.alarms.create("relay-reconnect", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener(connect);
chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(connect);
chrome.storage.onChanged.addListener((changes) => {
  if (changes.port || changes.token) reconnect();
});
chrome.tabs.onRemoved.addListener((tabId) => {
  if (tabId === drivenTab) drivenTab = null;
});
connect();

async function handle({ id, cmd, args }) {
  const { stopped } = await settings();
  if (stopped && cmd !== "release") {
    return { id, ok: false, error: "detenido por la persona" };
  }
  if (!Object.hasOwn(COMMANDS, cmd)) {
    return { id, ok: false, error: `comando desconocido: ${cmd}` };
  }
  try {
    return { id, ok: true, result: await COMMANDS[cmd](args || {}) };
  } catch (error) {
    return { id, ok: false, error: String(error.message || error) };
  }
}

async function currentTab() {
  if (drivenTab === null) throw new Error("no hay una pestaña controlada; la receta debe empezar con open");
  try {
    return await chrome.tabs.get(drivenTab);
  } catch {
    drivenTab = null;
    throw new Error("la persona cerró la pestaña controlada");
  }
}

async function run(func, ...args) {
  const tab = await currentTab();
  const [injection] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func, args });
  const result = injection ? injection.result : undefined;
  if (result && typeof result === "object" && result.__error) throw new Error(result.__error);
  return result;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitLoaded(tabId, timeoutMs = 30000) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    const tab = await chrome.tabs.get(tabId);
    if (tab.status === "complete" && tab.url && tab.url !== "about:blank") return tab;
    await sleep(150);
  }
  throw new Error("la página no terminó de cargar");
}

async function mark(tabId) {
  await chrome.action.setBadgeText({ tabId, text: BADGE });
  await chrome.action.setBadgeBackgroundColor({ tabId, color: "#c62828" });
  await chrome.scripting.executeScript({ target: { tabId }, files: ["banner.js"] });
}

async function unmark(tabId) {
  await chrome.action.setBadgeText({ tabId, text: "" });
  await chrome.scripting.executeScript({
    target: { tabId },
    func: () => document.getElementById("relay-banner-host")?.remove(),
  });
}

async function stop() {
  await chrome.storage.local.set({ stopped: true });
  if (drivenTab !== null) {
    try {
      await unmark(drivenTab);
    } catch {
      // The tab may be gone; nothing else to clean.
    }
  }
  if (ws && trusted) ws.send(JSON.stringify({ type: "event", event: "stopped" }));
}

chrome.runtime.onMessage.addListener((message, _sender, reply) => {
  if (message.type === "stop") {
    stop().then(() => reply({ stopped: true }));
  } else if (message.type === "resume") {
    chrome.storage.local.set({ stopped: false }).then(() => reply({ stopped: false }));
  } else if (message.type === "status") {
    settings().then((s) => reply({ connected: trusted, stopped: s.stopped, tab: drivenTab }));
  }
  return true;
});

// --- Functions injected into the page (they run in the page, not here) ---

function pageWait(selector, timeoutMs) {
  return new Promise((resolve) => {
    const end = Date.now() + timeoutMs;
    (function poll() {
      if (document.querySelector(selector)) return resolve(true);
      if (Date.now() > end) return resolve(false);
      setTimeout(poll, 150);
    })();
  });
}

function pageRead(items, fields) {
  const clean = (text) => (text || "").split("\n").map((l) => l.replace(/\s+/g, " ").trim()).filter(Boolean)
    .join("\n");
  const pick = (el, spec) => {
    if (el.matches("input[type=password]")) return null;
    const attr = spec.attr || "text";
    if (attr === "text") return clean(el.innerText);
    if (attr === "value") return el.value;
    if (attr === "href") return el.href || el.getAttribute("href");
    return el.getAttribute(attr);
  };
  const value = (root, raw) => {
    const spec = typeof raw === "string" ? { selector: raw } : raw;
    const els = [...root.querySelectorAll(spec.selector)];
    if (spec.heading) {
      const re = new RegExp(spec.heading, "i");
      const heading = els.find((e) => re.test(e.innerText));
      const next = heading && heading.nextElementSibling;
      return next ? clean(next.innerText) : null;
    }
    if (spec.label) {
      const el = els.find((e) => e.innerText.includes(spec.label));
      return el ? clean(el.innerText.replace(spec.label, "")) : null;
    }
    if (spec.all) return els.map((e) => pick(e, spec));
    return els.length ? pick(els[0], spec) : null;
  };
  const record = (root) => Object.fromEntries(Object.entries(fields).map(([k, s]) => [k, value(root, s)]));
  return items ? [...document.querySelectorAll(items)].map(record) : record(document);
}

function pageClick(selector) {
  const el = document.querySelector(selector);
  if (!el) return { __error: `estructura cambió: no existe ${selector}` };
  el.click();
  return true;
}

function pageFill(fields) {
  for (const [selector, value] of Object.entries(fields)) {
    const el = document.querySelector(selector);
    if (!el) return { __error: `estructura cambió: no existe ${selector}` };
    if (el.type === "password" || el.type === "file") {
      return { __error: `no se completan contraseñas ni archivos (${selector})` };
    }
    if (el.type === "checkbox" || el.type === "radio") {
      el.checked = value === true || value === "true" || value === "1";
    } else {
      const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype
        : el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }
  return true;
}

function pageFormValues(selector) {
  const form = document.querySelector(selector);
  if (!form) return { __error: `estructura cambió: no existe ${selector}` };
  const skip = new Set(["password", "file", "hidden", "submit", "button", "reset", "image"]);
  const out = {};
  for (const el of form.elements) {
    if (!el.name || skip.has(el.type)) continue;
    if (el.type === "checkbox") out[el.name] = el.checked;
    else if (el.type === "radio") { if (el.checked) out[el.name] = el.value; }
    else if (el.type === "select-multiple") out[el.name] = [...el.selectedOptions].map((o) => o.value);
    else out[el.name] = el.value;
  }
  return out;
}

function pageDetect() {
  const visible = (el) => el.offsetWidth > 0 && el.offsetHeight > 0;
  const frames = [...document.querySelectorAll("iframe[src]")].filter(visible);
  const challenge = /recaptcha\/(api2|enterprise)\/(anchor|bframe)(?!.*size=invisible)|hcaptcha\.com|challenges\.cloudflare\.com|turnstile|arkoselabs|funcaptcha/i;
  const frame = frames.find((f) => challenge.test(f.src));
  if (frame) return { blocked: true, signal: `iframe ${new URL(frame.src).hostname}` };
  const widget = document.querySelector(".g-recaptcha, .h-captcha, .cf-turnstile, #challenge-form, #cf-challenge-running");
  if (widget) return { blocked: true, signal: `elemento ${widget.className || widget.id}` };
  const text = `${document.title}\n${(document.body ? document.body.innerText : "").slice(0, 3000)}`;
  const phrase = text.match(/access denied|acceso denegado|verify you are human|verifica que eres humano|just a moment|unusual traffic|tráfico inusual|captcha/i);
  if (phrase) return { blocked: true, signal: `texto «${phrase[0]}»` };
  return { blocked: false };
}

// --- Commands ---

const COMMANDS = {
  async open({ url, hosts }) {
    if (!Array.isArray(hosts) || !hosts.includes(new URL(url).hostname)) {
      throw new Error(`${url} está fuera de los dominios de la receta`);
    }
    let tab = null;
    try {
      tab = drivenTab === null ? null : await chrome.tabs.get(drivenTab);
    } catch {
      tab = null;
    }
    if (tab) {
      await chrome.tabs.update(tab.id, { url });
      await sleep(300);
    } else {
      tab = await chrome.tabs.create({ url, active: false });
      drivenTab = tab.id;
    }
    const loaded = await waitLoaded(drivenTab);
    await mark(drivenTab);
    return { url: loaded.url, title: loaded.title };
  },
  async wait({ selector, timeout_ms: timeoutMs }) {
    if (!(await run(pageWait, selector, timeoutMs || 15000))) {
      throw new Error(`estructura cambió: no apareció ${selector}`);
    }
    return true;
  },
  async exists({ selector }) {
    return run((s) => Boolean(document.querySelector(s)), selector);
  },
  async read({ items, fields }) {
    return run(pageRead, items || null, fields);
  },
  async click({ selector, settle_ms: settleMs }) {
    await run(pageClick, selector);
    await sleep(settleMs || 800);
    const tab = await waitLoaded(drivenTab);
    await mark(drivenTab);
    return { url: tab.url };
  },
  async fill({ fields }) {
    return run(pageFill, fields);
  },
  async form_values({ form }) {
    return run(pageFormValues, form);
  },
  async detect() {
    return run(pageDetect);
  },
  async release() {
    if (drivenTab !== null) {
      try {
        await unmark(drivenTab);
      } catch {
        // Tab closed or not scriptable; nothing to clean.
      }
    }
    return true;
  },
};
