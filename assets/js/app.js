const $ = id => document.getElementById(id);
let activeQuery = "";

function makeCell(row, text, className = "") {
  const td = document.createElement("td");
  td.textContent = text || "—";
  if (className) td.className = className;
  row.appendChild(td);
  return td;
}

function makePill(online) {
  const span = document.createElement("span");
  span.className = `state-pill ${online ? "state-online" : "state-offline"}`;
  const dot = document.createElement("span");
  dot.className = "state-dot";
  span.append(dot, document.createTextNode(online ? "Disponível" : "Indisponível"));
  return span;
}

function formatDate(value) {
  if (!value) return "Não disponível";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("pt-BR");
}

async function refreshStatus() {
  $("refresh-state").textContent = "Consultando servidor...";
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();

    $("last-check").textContent = formatDate(data.timestamp);
    $("process-status").textContent = data.process.running ? "Em execução" : "Parado";
    $("process-detail").textContent = data.process.running ? `PID ${data.process.pid}` : "Processo não encontrado";
    const online = data.services.filter(s => s.online).length;
    $("ports-count").textContent = `${online} / ${data.services.length}`;
    $("log-status").textContent = data.log.exists ? "Encontrado" : "Não encontrado";
    $("log-detail").textContent = data.log.exists
      ? `${data.log.path.split("\\").pop()} · ${data.log.size.toLocaleString("pt-BR")} bytes`
      : data.log.path;
    $("pid").textContent = data.process.pid ?? "—";
    $("executable").textContent = data.process.executable ?? "Processo não encontrado";
    $("log-modified").textContent = data.log.modified ? formatDate(data.log.modified) : "Sem arquivo de log";

    const serviceBody = $("services-table");
    serviceBody.replaceChildren();
    for (const service of data.services) {
      const row = document.createElement("tr");
      makeCell(row, service.name);
      makeCell(row, String(service.port));
      const state = document.createElement("td");
      state.appendChild(makePill(service.online));
      row.appendChild(state);
      makeCell(row, `${data.proxy_ip}:${service.port}`);
      serviceBody.appendChild(row);
    }

    const problems = [];
    if (!data.process.running) problems.push("processo não encontrado");
    if (online !== data.services.length) problems.push(`${data.services.length - online} porta(s) indisponível(is)`);
    if (!data.log.exists) problems.push("arquivo de log ausente");
    $("alert-area").textContent = problems.length ? `Atenção: ${problems.join("; ")}.` : "";
    $("alert-area").classList.toggle("d-none", problems.length === 0);
    $("refresh-state").textContent = "Atualiza a cada 10 segundos";
  } catch (error) {
    $("alert-area").textContent = `Falha ao consultar o backend: ${error.message}`;
    $("alert-area").classList.remove("d-none");
    $("refresh-state").textContent = "Falha na atualização";
  }
}

async function refreshLogs() {
  const body = $("logs-table");
  body.replaceChildren();
  const loading = document.createElement("tr");
  const cell = document.createElement("td");
  cell.colSpan = 7;
  cell.textContent = "Carregando registros...";
  loading.appendChild(cell);
  body.appendChild(loading);

  try {
    const params = new URLSearchParams({ limit: "100", q: activeQuery });
    const response = await fetch(`/api/logs?${params}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    body.replaceChildren();

    if (!data.items.length) {
      const row = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 7;
      td.className = "text-secondary py-4";
      td.textContent = data.error || "Nenhum registro corresponde ao filtro.";
      row.appendChild(td);
      body.appendChild(row);
    } else {
      for (const item of data.items.slice().reverse()) {
        const row = document.createElement("tr");
        makeCell(row, `${item.date} ${item.time}`);
        makeCell(row, item.service);
        makeCell(row, item.client);
        makeCell(row, item.destination, "log-destination");
        const status = makeCell(row, item.status, "status-code");
        status.title = item.raw;
        makeCell(row, item.sent);
        makeCell(row, item.received);
        body.appendChild(row);
      }
    }

    $("logs-info").textContent =
      `${data.file || "Sem arquivo"} · ${data.returned} registro(s) exibido(s)` +
      (activeQuery ? ` · filtro: ${activeQuery}` : "") +
      (data.truncated ? " · leitura limitada aos últimos 2 MB" : "");
  } catch (error) {
    body.replaceChildren();
    const row = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 7;
    td.textContent = `Erro ao carregar logs: ${error.message}`;
    row.appendChild(td);
    body.appendChild(row);
    $("logs-info").textContent = "Falha na consulta";
  }
}

$("logs-search").addEventListener("submit", event => {
  event.preventDefault();
  activeQuery = $("log-query").value.trim();
  refreshLogs();
});
$("logs-clear").addEventListener("click", () => {
  $("log-query").value = "";
  activeQuery = "";
  refreshLogs();
});
$("logs-refresh").addEventListener("click", refreshLogs);

refreshStatus();
refreshLogs();
setInterval(refreshStatus, 10000);
setInterval(refreshLogs, 10000);

// LDA 3proxy Monitor - estatísticas históricas
function statsFormatBytes(value) {
  if (!Number.isFinite(Number(value))) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let n = Number(value), i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toLocaleString("pt-BR", { maximumFractionDigits: 2 })} ${units[i]}`;
}

function statsRenderList(id, items) {
  const root = document.getElementById(id);
  if (!root) return;
  root.replaceChildren();

  if (!items || !items.length) {
    root.textContent = "Sem dados disponíveis.";
    return;
  }

  const max = Math.max(...items.map(x => Number(x.count) || 0), 1);
  for (const item of items) {
    const row = document.createElement("div");
    row.className = "rank-row";

    const label = document.createElement("div");
    label.className = "rank-label";
    label.textContent = item.name ?? `Status ${item.code ?? ""}`;
    label.title = label.textContent;

    const count = document.createElement("span");
    count.className = "rank-count";
    count.textContent = Number(item.count).toLocaleString("pt-BR");

    const track = document.createElement("div");
    track.className = "rank-track";
    const fill = document.createElement("div");
    fill.className = "rank-fill";
    fill.style.width = `${Math.max(2, (Number(item.count) || 0) / max * 100)}%`;
    track.appendChild(fill);

    row.append(label, count);
    root.append(row, track);
  }
}

async function refreshStats() {
  const period = document.getElementById("stats-period");
  try {
    const response = await fetch("/api/stats", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();

    document.getElementById("stat-records").textContent =
      Number(data.records || 0).toLocaleString("pt-BR");
    document.getElementById("stat-sent").textContent =
      statsFormatBytes(data.sent_bytes);
    document.getElementById("stat-received").textContent =
      statsFormatBytes(data.received_bytes);
    document.getElementById("stat-status-count").textContent =
      String((data.statuses || []).length);

    period.textContent = `${data.files_count} arquivo(s): ${(data.files || []).join(", ")}`;
    document.getElementById("stats-updated").textContent =
      `Atualizado: ${new Date(data.generated_at).toLocaleString("pt-BR")}`;

    statsRenderList("stats-status-list", (data.statuses || []).map(x => ({
      name: `Status ${x.code}`, count: x.count
    })));
    statsRenderList("stats-clients", data.top_clients || []);
    statsRenderList("stats-destinations", data.top_destinations || []);

    const chart = document.getElementById("stats-hourly");
    chart.replaceChildren();
    const points = data.hourly || [];

    if (!points.length) {
      chart.textContent = "Sem dados de horário.";
    } else {
      const max = Math.max(...points.map(x => Number(x.count) || 0), 1);
      for (const point of points) {
        const column = document.createElement("div");
        column.className = "hour-bar-wrap";

        const count = document.createElement("div");
        count.className = "hour-count";
        count.textContent = Number(point.count).toLocaleString("pt-BR");

        const track = document.createElement("div");
        track.className = "hour-track";
        const fill = document.createElement("div");
        fill.className = "hour-fill";
        fill.style.height = `${Math.max(3, (Number(point.count) || 0) / max * 100)}%`;
        track.appendChild(fill);

        const label = document.createElement("div");
        label.className = "hour-label";
        label.textContent = String(point.hour).slice(-5);
        label.title = point.hour;

        column.append(count, track, label);
        chart.appendChild(column);
      }
    }
  } catch (error) {
    if (period) period.textContent = `Erro ao carregar estatísticas: ${error.message}`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  refreshStats();
  setInterval(refreshStats, 60000);
});
