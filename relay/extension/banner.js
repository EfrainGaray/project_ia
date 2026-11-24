// Visible banner on the driven tab, with a stop button. Injected by the service worker.
(() => {
  if (document.getElementById("relay-banner-host")) return;
  const host = document.createElement("div");
  host.id = "relay-banner-host";
  host.style.cssText = "position:fixed;top:0;left:0;right:0;z-index:2147483647;";
  const root = host.attachShadow({ mode: "open" });
  root.innerHTML = `
    <style>
      .bar { display:flex; gap:12px; align-items:center; justify-content:center; padding:6px 12px;
             font:14px/1.4 system-ui, sans-serif; background:#c62828; color:#fff; }
      button { font:inherit; font-weight:600; padding:2px 12px; border:0; border-radius:4px; cursor:pointer;
               background:#fff; color:#c62828; }
    </style>
    <div class="bar" role="status">
      <span>El asistente está controlando esta pestaña. Nada se envía sin tu aprobación.</span>
      <button type="button" id="relay-stop">Detener</button>
    </div>`;
  root.getElementById("relay-stop").addEventListener("click", () => {
    chrome.runtime.sendMessage({ type: "stop" });
  });
  document.documentElement.appendChild(host);
})();
