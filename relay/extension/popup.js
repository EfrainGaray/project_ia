const $ = (id) => document.getElementById(id);

async function refresh() {
  const status = await chrome.runtime.sendMessage({ type: "status" });
  const parts = [status.connected ? "Conectado al servicio local." : "Sin conexión con el servicio local."];
  parts.push(status.stopped ? "Detenido: no acepta comandos." : "Activo.");
  if (status.tab !== null) parts.push(`Pestaña controlada: ${status.tab}.`);
  $("status").textContent = parts.join(" ");
}

async function load() {
  const { port, token } = await chrome.storage.local.get({ port: 8765, token: "" });
  $("port").value = port;
  $("token").value = token;
  await refresh();
}

$("stop").addEventListener("click", async () => {
  await chrome.runtime.sendMessage({ type: "stop" });
  await refresh();
});
$("resume").addEventListener("click", async () => {
  await chrome.runtime.sendMessage({ type: "resume" });
  await refresh();
});
$("save").addEventListener("click", async () => {
  await chrome.storage.local.set({ token: $("token").value.trim(), port: Number($("port").value) || 8765 });
  setTimeout(refresh, 500);
});
load();
