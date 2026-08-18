"""Self-contained local dashboard for the ChatEvent Observatory."""

DASHBOARD_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ChatEvent Observatory</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0a0c10;
      --panel: rgba(20, 24, 31, .82);
      --panel-strong: #171b23;
      --line: rgba(255, 255, 255, .09);
      --muted: #929aaa;
      --text: #f5f7fb;
      --accent: #b9ff66;
      --accent-soft: rgba(185, 255, 102, .12);
      --blue: #77b8ff;
      --orange: #ffb86b;
      --danger: #ff7272;
      --radius: 16px;
      font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      background:
        radial-gradient(circle at 20% -10%, rgba(91, 120, 255, .16), transparent 34%),
        radial-gradient(circle at 90% 0%, rgba(185, 255, 102, .08), transparent 28%),
        var(--bg);
    }
    button, input, select { font: inherit; }
    button { cursor: pointer; }
    .shell { max-width: 1480px; margin: 0 auto; padding: 28px; }
    header { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; margin-bottom: 26px; }
    .eyebrow { color: var(--accent); font: 700 12px/1.2 ui-monospace, SFMono-Regular, monospace; letter-spacing: .14em; text-transform: uppercase; }
    h1 { margin: 8px 0 5px; font-size: clamp(28px, 4vw, 48px); letter-spacing: -.045em; }
    header p { margin: 0; color: var(--muted); max-width: 660px; }
    .live { display: flex; align-items: center; gap: 9px; padding: 9px 13px; border: 1px solid var(--line); border-radius: 999px; color: #cbd2df; background: rgba(255,255,255,.03); white-space: nowrap; }
    .live::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 16px var(--accent); }
    .stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }
    .card, .panel { border: 1px solid var(--line); background: var(--panel); backdrop-filter: blur(18px); border-radius: var(--radius); }
    .card { padding: 17px 18px; }
    .card small { color: var(--muted); display: block; margin-bottom: 9px; }
    .metric { font-size: 29px; font-weight: 720; letter-spacing: -.04em; }
    .metric-note { color: var(--muted); font-size: 12px; margin-left: 7px; }
    .workspace { display: grid; grid-template-columns: 330px minmax(0, 1fr); gap: 16px; align-items: start; }
    .panel { overflow: hidden; }
    .panel-head { min-height: 64px; padding: 16px 17px; display: flex; align-items: center; justify-content: space-between; gap: 12px; border-bottom: 1px solid var(--line); }
    .panel-head h2 { margin: 0; font-size: 15px; }
    .panel-head span { color: var(--muted); font-size: 12px; }
    .button { border: 1px solid var(--line); border-radius: 10px; padding: 8px 11px; color: var(--text); background: rgba(255,255,255,.04); }
    .button:hover { border-color: rgba(185,255,102,.45); background: var(--accent-soft); }
    .button.primary { color: #10150b; background: var(--accent); border-color: var(--accent); font-weight: 700; }
    .subscriptions { padding: 9px; display: grid; gap: 7px; }
    .subscription { padding: 12px; border-radius: 12px; border: 1px solid transparent; background: rgba(255,255,255,.025); }
    .subscription:hover { border-color: var(--line); }
    .subscription-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
    .subscription strong { font-size: 13px; }
    .subscription p { margin: 7px 0; color: #c8cfdb; font: 12px/1.5 ui-monospace, SFMono-Regular, monospace; overflow-wrap: anywhere; }
    .chips { display: flex; flex-wrap: wrap; gap: 5px; }
    .chip { padding: 3px 7px; border-radius: 999px; font: 600 10px/1.4 ui-monospace, SFMono-Regular, monospace; color: var(--muted); background: rgba(255,255,255,.05); }
    .chip.webhook, .chip.event_queue, .chip.gateway_forward { color: var(--blue); background: rgba(119,184,255,.1); }
    .chip.api_cursor, .chip.poll, .chip.manual_backfill { color: var(--orange); background: rgba(255,184,107,.1); }
    .chip.push { color: var(--blue); background: rgba(119,184,255,.1); }
    .chip.pull { color: var(--orange); background: rgba(255,184,107,.1); }
    .platforms { padding: 9px; display: grid; gap: 9px; border-top: 1px solid var(--line); }
    .platform { padding: 12px; border-radius: 12px; background: rgba(255,255,255,.025); }
    .platform p { margin: 7px 0 9px; color: #c8cfdb; font: 12px/1.5 ui-monospace, SFMono-Regular, monospace; overflow-wrap: anywhere; }
    .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); }
    .dot.off { background: #555d6b; }
    .filters { display: grid; grid-template-columns: minmax(170px, 1fr) 150px 190px; gap: 8px; padding: 12px 14px; border-bottom: 1px solid var(--line); }
    .control { width: 100%; height: 38px; border: 1px solid var(--line); border-radius: 10px; padding: 0 11px; color: var(--text); background: #11151c; outline: none; }
    .control:focus { border-color: rgba(185,255,102,.55); box-shadow: 0 0 0 3px rgba(185,255,102,.08); }
    .event-head, .event-row { display: grid; grid-template-columns: 112px minmax(160px, 1fr) minmax(140px, .8fr) 145px 72px; gap: 14px; align-items: center; }
    .event-head { padding: 10px 15px; color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: .1em; border-bottom: 1px solid var(--line); }
    .event-list { max-height: 650px; overflow: auto; }
    .event-row { width: 100%; padding: 14px 15px; color: inherit; text-align: left; border: 0; border-bottom: 1px solid rgba(255,255,255,.055); background: transparent; }
    .event-row:hover { background: rgba(255,255,255,.035); }
    .source { color: var(--accent); font: 700 12px ui-monospace, SFMono-Regular, monospace; }
    .kind { font: 600 12px ui-monospace, SFMono-Regular, monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .summary { color: #b5bdca; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    time { color: var(--muted); font-size: 11px; }
    .count { text-align: right; font: 700 11px ui-monospace, SFMono-Regular, monospace; color: var(--muted); }
    .empty { padding: 54px 22px; text-align: center; color: var(--muted); }
    .empty strong { color: var(--text); display: block; margin-bottom: 7px; }
    .detail { position: fixed; inset: 0; z-index: 20; display: none; background: rgba(2,4,7,.66); backdrop-filter: blur(6px); }
    .detail.open { display: block; }
    .detail-panel { width: min(720px, 92vw); height: 100%; margin-left: auto; padding: 24px; overflow: auto; border-left: 1px solid var(--line); background: #101319; box-shadow: -30px 0 80px rgba(0,0,0,.35); }
    .detail-top { display: flex; justify-content: space-between; align-items: center; gap: 14px; }
    .detail h2 { margin: 18px 0 6px; letter-spacing: -.03em; overflow-wrap: anywhere; }
    .detail-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px; margin: 18px 0; }
    .field { padding: 11px; border: 1px solid var(--line); border-radius: 11px; background: rgba(255,255,255,.025); }
    .field small { color: var(--muted); display: block; margin-bottom: 6px; }
    .field div { font: 12px/1.5 ui-monospace, SFMono-Regular, monospace; overflow-wrap: anywhere; }
    .json-title { display: flex; justify-content: space-between; align-items: center; margin: 18px 0 8px; }
    pre { margin: 0; padding: 14px; border: 1px solid var(--line); border-radius: 12px; color: #d5dbea; background: #090b0f; overflow: auto; font: 11px/1.65 ui-monospace, SFMono-Regular, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
    dialog { width: min(540px, calc(100vw - 28px)); color: var(--text); border: 1px solid var(--line); border-radius: 18px; background: #151921; box-shadow: 0 40px 100px rgba(0,0,0,.55); }
    dialog::backdrop { background: rgba(0,0,0,.62); backdrop-filter: blur(5px); }
    dialog h2 { margin: 4px 0 18px; }
    .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    label { color: var(--muted); font-size: 12px; }
    label .control { margin-top: 6px; }
    .wide { grid-column: 1 / -1; }
    .checks { display: flex; gap: 16px; padding-top: 10px; }
    .checks label { color: var(--text); }
    .dialog-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 20px; }
    .error { color: var(--danger); font-size: 12px; min-height: 18px; margin-top: 8px; }
    @media (max-width: 900px) {
      .stats { grid-template-columns: repeat(2, 1fr); }
      .workspace { grid-template-columns: 1fr; }
      .event-head { display: none; }
      .event-row { grid-template-columns: 90px 1fr 60px; }
      .event-row .summary, .event-row time { display: none; }
      .subscriptions { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 580px) {
      .shell { padding: 18px 12px; }
      header { display: block; }
      .live { display: inline-flex; margin-top: 14px; }
      .filters { grid-template-columns: 1fr; }
      .subscriptions { grid-template-columns: 1fr; }
      .detail-grid, .form-grid { grid-template-columns: 1fr; }
      .wide { grid-column: auto; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <div>
        <div class="eyebrow">Event Capture / Phase 1</div>
        <h1>ChatEvent Observatory</h1>
        <p>看清订阅了什么、捕获到了什么，以及原始事件如何被规范化。</p>
      </div>
      <div class="live" id="liveStatus">本地事件流 · 5 秒刷新</div>
    </header>

    <section class="stats">
      <article class="card"><small>标准事件</small><span class="metric" id="eventCount">0</span></article>
      <article class="card"><small>启用订阅</small><span class="metric" id="subscriptionCount">0</span></article>
      <article class="card"><small>事件来源</small><span class="metric" id="sourceCount">0</span></article>
      <article class="card"><small>重复投递</small><span class="metric" id="duplicateCount">0</span><span class="metric-note">已去重</span></article>
    </section>

    <section class="workspace">
      <aside class="panel">
        <div class="panel-head">
          <div><h2>Subscriptions</h2><span>当前关注对象</span></div>
          <button class="button" id="addSubscription">＋ 新建</button>
        </div>
        <div class="subscriptions" id="subscriptions"></div>
        <div class="panel-head">
          <div><h2>Platform actions</h2><span>v0.1 可控事件目录</span></div>
        </div>
        <div class="platforms" id="platforms"></div>
      </aside>

      <section class="panel">
        <div class="panel-head">
          <div><h2>Event stream</h2><span id="resultCount">0 条记录</span></div>
          <button class="button" id="refresh">刷新</button>
        </div>
        <div class="filters">
          <input class="control" id="search" placeholder="搜索 payload、actor 或 conversation…" />
          <select class="control" id="sourceFilter"><option value="">全部来源</option></select>
          <select class="control" id="kindFilter"><option value="">全部事件类型</option></select>
          <select class="control" id="timeFilter">
            <option value="">全部时间</option>
            <option value="1">最近 24 小时</option>
            <option value="3">最近 3 天</option>
            <option value="7">最近 7 天</option>
            <option value="30">最近 30 天</option>
          </select>
          <input class="control" id="fromFilter" type="datetime-local" title="开始时间" />
          <input class="control" id="toFilter" type="datetime-local" title="结束时间" />
        </div>
        <div class="event-head"><span>Source</span><span>Kind</span><span>Summary</span><span>Captured</span><span>Seen</span></div>
        <div class="event-list" id="events"></div>
      </section>
    </section>
  </main>

  <section class="detail" id="detail" aria-hidden="true">
    <aside class="detail-panel">
      <div class="detail-top"><div class="eyebrow">Normalized event</div><button class="button" id="closeDetail">关闭</button></div>
      <h2 id="detailTitle"></h2>
      <div class="chips" id="detailChips"></div>
      <div class="detail-grid" id="detailFields"></div>
      <div class="json-title"><strong>Normalized payload</strong></div><pre id="normalizedJson"></pre>
      <div class="json-title"><strong>Raw payload</strong><button class="button" id="copyRaw">复制 JSON</button></div><pre id="rawJson"></pre>
    </aside>
  </section>

  <dialog id="subscriptionDialog">
    <form id="subscriptionForm">
      <div class="eyebrow">Observe a target</div>
      <h2>新建订阅</h2>
      <div class="form-grid">
        <label>显示名称<input class="control" name="label" placeholder="核心仓库 Issues" /></label>
        <label>平台 source<select class="control" name="source" id="subscriptionSource" required><option value="">选择平台</option></select></label>
        <label class="wide">关注目标<input class="control" name="target" required placeholder="repo:ChatArch/ChatEvent / stream:demo/topic:loop" /></label>
        <label class="wide">事件类型<input class="control" name="eventKinds" value="*" placeholder="issue.opened, pull_request.merged" /></label>
        <div class="wide checks">
          <label><input type="checkbox" name="mode" value="webhook" checked /> webhook</label>
          <label><input type="checkbox" name="mode" value="event_queue" /> event_queue</label>
          <label><input type="checkbox" name="mode" value="api_cursor" /> api_cursor</label>
          <label><input type="checkbox" name="mode" value="poll" /> poll</label>
        </div>
      </div>
      <div class="error" id="formError"></div>
      <div class="dialog-actions">
        <button type="button" class="button" id="cancelSubscription">取消</button>
        <button type="submit" class="button primary">保存订阅</button>
      </div>
    </form>
  </dialog>

  <script>
    const state = { events: [], stats: {}, platforms: [], detail: null };
    const $ = (id) => document.getElementById(id);
    const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
    const formatTime = (value) => value ? new Intl.DateTimeFormat("zh-CN", {month:"2-digit", day:"2-digit", hour:"2-digit", minute:"2-digit", second:"2-digit"}).format(new Date(value)) : "—";
    const localDateTimeToIso = (value) => value ? new Date(value).toISOString() : "";
    const api = async (path, options = {}) => {
      const response = await fetch(path, {headers: {"Content-Type": "application/json"}, ...options});
      if (!response.ok) throw new Error((await response.json()).detail || response.statusText);
      return response.json();
    };

    function summary(event) {
      const payload = event.payload || {};
      return payload.title || payload.subject || payload.content || payload.message || event.conversation_id || event.subject_id || event.id;
    }

    function renderStats(stats) {
      $("eventCount").textContent = stats.event_count || 0;
      $("subscriptionCount").textContent = stats.subscription_count || 0;
      $("sourceCount").textContent = stats.source_count || 0;
      $("duplicateCount").textContent = stats.duplicate_count || 0;
      updateOptions("sourceFilter", "全部来源", Object.keys(stats.sources || {}));
      updateOptions("kindFilter", "全部事件类型", Object.keys(stats.kinds || {}));
    }

    function updateOptions(id, label, values) {
      const select = $(id); const current = select.value;
      select.innerHTML = `<option value="">${escapeHtml(label)}</option>` + values.map(value => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("");
      select.value = values.includes(current) ? current : "";
    }

    function renderSubscriptions(items) {
      const root = $("subscriptions");
      if (!items.length) {
        root.innerHTML = `<div class="empty"><strong>还没有订阅</strong>先记录要关注的平台与对象。</div>`;
        return;
      }
      root.innerHTML = items.map(item => `
        <article class="subscription">
          <div class="subscription-top"><strong>${escapeHtml(item.label || item.source)}</strong><span class="dot ${item.enabled ? "" : "off"}"></span></div>
          <p>${escapeHtml(item.target)}</p>
          <div class="chips">
            <span class="chip">${escapeHtml(item.source)}</span>
            ${item.capture_modes.map(mode => `<span class="chip ${escapeHtml(mode)}">${escapeHtml(mode)}</span>`).join("")}
            <span class="chip">${escapeHtml(item.event_kinds.join(", "))}</span>
          </div>
        </article>`).join("");
    }

    function renderPlatforms(platforms) {
      state.platforms = platforms;
      const root = $("platforms");
      if (!platforms.length) {
        root.innerHTML = `<div class="empty"><strong>还没有平台目录</strong>/api/platforms 暂无返回。</div>`;
        return;
      }
      root.innerHTML = platforms.map(platform => `
        <article class="platform">
          <div class="subscription-top"><strong>${escapeHtml(platform.display_name)}</strong><span class="chip">${escapeHtml(platform.id)}</span></div>
          <p>scope: ${escapeHtml(platform.scope_examples.slice(0, 2).join(" / "))}</p>
          <div class="chips">
            ${platform.primary_acquisition_modes.map(mode => `<span class="chip ${escapeHtml(mode)}">${escapeHtml(mode)}</span>`).join("")}
          </div>
          <p>actions:</p>
          <div class="chips">
            ${platform.actions.slice(0, 12).map(action => `<span class="chip" title="${escapeHtml(action.description)}">${escapeHtml(action.kind)}</span>`).join("")}
          </div>
        </article>`).join("");
      const source = $("subscriptionSource");
      const current = source.value;
      source.innerHTML = `<option value="">选择平台</option>` + platforms.map(platform => `<option value="${escapeHtml(platform.id)}">${escapeHtml(platform.display_name)} · ${escapeHtml(platform.id)}</option>`).join("");
      source.value = platforms.some(platform => platform.id === current) ? current : "";
    }

    function renderEvents(items) {
      state.events = items;
      $("resultCount").textContent = `${items.length} 条记录`;
      const root = $("events");
      if (!items.length) {
        root.innerHTML = `<div class="empty"><strong>等待第一条事件</strong>通过 POST /api/events 写入标准 ChatEvent。</div>`;
        return;
      }
      root.innerHTML = items.map((item, index) => {
        const event = item.event;
        return `<button class="event-row" data-index="${index}">
          <span class="source">${escapeHtml(event.source)}</span>
          <span class="kind">${escapeHtml(event.kind)}</span>
          <span class="summary">${escapeHtml(summary(event))}</span>
          <time>${escapeHtml(formatTime(event.captured_at))}</time>
          <span class="count">×${item.seen_count}</span>
        </button>`;
      }).join("");
      root.querySelectorAll(".event-row").forEach(row => row.addEventListener("click", () => openDetail(items[Number(row.dataset.index)])));
    }

    function field(label, value) {
      return `<div class="field"><small>${escapeHtml(label)}</small><div>${escapeHtml(value || "—")}</div></div>`;
    }

    function openDetail(item) {
      state.detail = item;
      const event = item.event;
      $("detailTitle").textContent = `${event.source}:${event.id}`;
      $("detailChips").innerHTML = `<span class="chip">${escapeHtml(event.kind)}</span><span class="chip ${escapeHtml(event.capture_mode)}">${escapeHtml(event.capture_mode)}</span><span class="chip">seen ×${item.seen_count}</span>`;
      $("detailFields").innerHTML = [
        field("Occurred", formatTime(event.occurred_at)),
        field("Captured", formatTime(event.captured_at)),
        field("Subscription", event.subscription_id),
        field("Conversation", event.conversation_id),
        field("Actor", event.actor_id),
        field("Subject", [event.subject_type, event.subject_id].filter(Boolean).join(":")),
        field("Cursor", event.cursor),
        field("URL", event.url),
      ].join("");
      $("normalizedJson").textContent = JSON.stringify(event.payload || {}, null, 2);
      $("rawJson").textContent = JSON.stringify(event.raw_payload ?? {}, null, 2);
      $("detail").classList.add("open"); $("detail").setAttribute("aria-hidden", "false");
    }

    function closeDetail() { $("detail").classList.remove("open"); $("detail").setAttribute("aria-hidden", "true"); }

    async function loadAll() {
      try {
        const params = new URLSearchParams();
        if ($("sourceFilter").value) params.set("source", $("sourceFilter").value);
        if ($("kindFilter").value) params.set("kind", $("kindFilter").value);
        if ($("timeFilter").value) params.set("days", $("timeFilter").value);
        if ($("fromFilter").value) params.set("from", localDateTimeToIso($("fromFilter").value));
        if ($("toFilter").value) params.set("to", localDateTimeToIso($("toFilter").value));
        if ($("search").value.trim()) params.set("q", $("search").value.trim());
        const [stats, subscriptions, events, platforms] = await Promise.all([
          api("/api/stats"), api("/api/subscriptions"), api(`/api/events?${params}`), api("/api/platforms")
        ]);
        renderStats(stats); renderSubscriptions(subscriptions); renderPlatforms(platforms.items); renderEvents(events.items);
        $("liveStatus").textContent = `本地事件流 · ${formatTime(stats.latest_captured_at)}`;
      } catch (error) {
        $("liveStatus").textContent = `连接失败 · ${error.message}`;
      }
    }

    let debounce;
    $("search").addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(loadAll, 260); });
    $("sourceFilter").addEventListener("change", loadAll);
    $("kindFilter").addEventListener("change", loadAll);
    $("timeFilter").addEventListener("change", loadAll);
    $("fromFilter").addEventListener("change", loadAll);
    $("toFilter").addEventListener("change", loadAll);
    $("refresh").addEventListener("click", loadAll);
    $("closeDetail").addEventListener("click", closeDetail);
    $("detail").addEventListener("click", event => { if (event.target === $("detail")) closeDetail(); });
    $("copyRaw").addEventListener("click", async () => navigator.clipboard.writeText($("rawJson").textContent));

    const dialog = $("subscriptionDialog");
    $("addSubscription").addEventListener("click", () => dialog.showModal());
    $("cancelSubscription").addEventListener("click", () => dialog.close());
    $("subscriptionForm").addEventListener("submit", async event => {
      event.preventDefault(); $("formError").textContent = "";
      const formElement = event.currentTarget;
      const form = new FormData(formElement);
      const captureModes = Array.from(formElement.querySelectorAll('input[name="mode"]:checked')).map(input => input.value);
      if (!captureModes.length) { $("formError").textContent = "至少选择一种捕获方式。"; return; }
      const body = {
        label: form.get("label") || null,
        source: form.get("source"),
        target: form.get("target"),
        event_kinds: String(form.get("eventKinds") || "*").split(",").map(value => value.trim()).filter(Boolean),
        capture_modes: captureModes,
      };
      try {
        await api("/api/subscriptions", {method: "POST", body: JSON.stringify(body)});
        formElement.reset(); dialog.close(); await loadAll();
      } catch (error) { $("formError").textContent = error.message; }
    });

    loadAll(); setInterval(loadAll, 5000);
  </script>
</body>
</html>"""
