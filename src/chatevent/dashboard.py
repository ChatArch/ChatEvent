"""Self-contained local dashboard for the ChatEvent Observatory."""

LOGIN_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ChatEvent Login</title>
  <style>
    :root { color-scheme: dark; --bg: #080a0d; --card: rgba(18,22,29,.86); --line: rgba(255,255,255,.1); --text: #f6f8fb; --muted: #9aa4b4; --accent: #b9ff66; --danger: #ff7272; font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 24px; color: var(--text); background: radial-gradient(circle at 15% 10%, rgba(185,255,102,.14), transparent 30%), radial-gradient(circle at 90% 20%, rgba(119,184,255,.13), transparent 34%), var(--bg); }
    .login-card { width: min(440px, 100%); padding: 28px; border: 1px solid var(--line); border-radius: 24px; background: var(--card); box-shadow: 0 40px 100px rgba(0,0,0,.45); }
    .eyebrow { color: var(--accent); font: 700 12px/1.2 ui-monospace, SFMono-Regular, monospace; letter-spacing: .14em; text-transform: uppercase; }
    h1 { margin: 10px 0 8px; font-size: clamp(30px, 8vw, 46px); letter-spacing: -.05em; }
    p { margin: 0 0 20px; color: var(--muted); line-height: 1.6; }
    label { display: block; color: var(--muted); font-size: 12px; }
    input { width: 100%; height: 44px; margin-top: 7px; padding: 0 12px; border: 1px solid var(--line); border-radius: 12px; color: var(--text); background: #10151d; outline: none; font: 13px ui-monospace, SFMono-Regular, monospace; }
    input:focus { border-color: rgba(185,255,102,.6); box-shadow: 0 0 0 3px rgba(185,255,102,.1); }
    button { width: 100%; height: 44px; margin-top: 14px; border: 0; border-radius: 12px; color: #10150b; background: var(--accent); font-weight: 760; cursor: pointer; }
    .links { display: flex; gap: 10px; margin-top: 16px; }
    a { color: var(--muted); text-decoration: none; font-size: 12px; }
    a:hover { color: var(--accent); }
    .error { min-height: 18px; margin-top: 10px; color: var(--danger); font-size: 12px; }
  </style>
</head>
<body>
  <main class="login-card">
    <div class="eyebrow">ChatEvent / Login</div>
    <h1>登录 Observatory</h1>
    <p>登录后才能查看事件流、订阅和用户管理。Token 不是网页登录凭据，只用于 CLI、模型或程序代表你的账号调用 API。</p>
    <form id="loginForm">
      <label>账号<input id="usernameInput" name="username" placeholder="you@example.com" autocomplete="username" spellcheck="false" autofocus /></label>
      <label>密码<input id="passwordInput" name="password" type="password" autocomplete="current-password" /></label>
      <button type="submit">进入 Observatory</button>
      <div class="error" id="loginError"></div>
    </form>
    <div class="links">
      <a href="https://github.com/ChatArch/ChatEvent" target="_blank" rel="noreferrer">GitHub</a>
      <a href="https://arch.gh.wzhecnu.cn/ChatEvent/" target="_blank" rel="noreferrer">Docs</a>
    </div>
  </main>
  <script>
    document.getElementById("loginForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const username = document.getElementById("usernameInput").value.trim();
      const password = document.getElementById("passwordInput").value;
      const error = document.getElementById("loginError");
      if (!username || !password) { error.textContent = "请输入账号和密码。"; return; }
      try {
        const response = await fetch("/api/login", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({username, password})});
        if (!response.ok) throw new Error((await response.json()).detail || "login failed");
        window.location.reload();
      } catch (err) { error.textContent = `登录失败：${err.message}`; }
    });
  </script>
</body>
</html>"""

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
      --control-bg: #11151c;
      --detail-bg: #101319;
      --dialog-bg: #151921;
      --code-bg: #090b0f;
      --soft-text: #c8cfdb;
      --target-text: #d7dfeb;
      --active-ink: #10150b;
      --glass: rgba(255,255,255,.03);
      --row-hover: rgba(255,255,255,.035);
      font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    :root[data-theme="light"] {
      color-scheme: light;
      --bg: #f6f4ef;
      --panel: rgba(255, 255, 255, .86);
      --panel-strong: #ffffff;
      --line: rgba(13, 17, 23, .14);
      --muted: #606875;
      --text: #121417;
      --accent: #111111;
      --accent-soft: rgba(0, 0, 0, .07);
      --blue: #095fc6;
      --orange: #a65300;
      --danger: #c62828;
      --control-bg: #ffffff;
      --detail-bg: #ffffff;
      --dialog-bg: #ffffff;
      --code-bg: #f0eee8;
      --soft-text: #38404c;
      --target-text: #111111;
      --active-ink: #ffffff;
      --glass: rgba(0,0,0,.035);
      --row-hover: rgba(0,0,0,.045);
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
    .header-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; max-width: 440px; }
    .icon-link { display: inline-flex; align-items: center; gap: 7px; min-height: 38px; padding: 8px 11px; border: 1px solid var(--line); border-radius: 999px; color: var(--text); background: var(--glass); text-decoration: none; }
    .icon-link:hover { border-color: rgba(185,255,102,.45); background: var(--accent-soft); }
    .icon-link svg { width: 16px; height: 16px; fill: currentColor; }
    .theme-toggle { min-height: 38px; border-radius: 999px; }
    .eyebrow { color: var(--accent); font: 700 12px/1.2 ui-monospace, SFMono-Regular, monospace; letter-spacing: .14em; text-transform: uppercase; }
    h1 { margin: 8px 0 5px; font-size: clamp(28px, 4vw, 48px); letter-spacing: -.045em; }
    header p { margin: 0; color: var(--muted); max-width: 660px; }
    .live { display: flex; align-items: center; gap: 9px; padding: 9px 13px; border: 1px solid var(--line); border-radius: 999px; color: var(--soft-text); background: var(--glass); white-space: nowrap; }
    .live::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 16px var(--accent); }
    .stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }
    .card, .panel { border: 1px solid var(--line); background: var(--panel); backdrop-filter: blur(18px); border-radius: var(--radius); }
    .card { padding: 17px 18px; }
    .card small { color: var(--muted); display: block; margin-bottom: 9px; }
    .metric { font-size: 29px; font-weight: 720; letter-spacing: -.04em; }
    .metric-note { color: var(--muted); font-size: 12px; margin-left: 7px; }
    .tabs { display: inline-flex; flex-wrap: wrap; gap: 6px; max-width: 100%; margin: 0 0 14px; padding: 6px; border: 1px solid var(--line); border-radius: 999px; background: rgba(255,255,255,.025); }
    .tab { display: inline-flex; align-items: center; gap: 8px; border: 1px solid transparent; border-radius: 999px; padding: 10px 14px; color: var(--muted); background: transparent; }
    .tab:hover { color: var(--text); border-color: rgba(255,255,255,.08); background: rgba(255,255,255,.04); }
    .tab.active { color: var(--active-ink); background: var(--accent); border-color: var(--accent); font-weight: 760; }
    .tab-count { min-width: 22px; padding: 2px 7px; border-radius: 999px; color: var(--text); background: rgba(255,255,255,.08); font: 700 11px/1.5 ui-monospace, SFMono-Regular, monospace; text-align: center; }
    .tab.active .tab-count { color: var(--active-ink); background: rgba(255,255,255,.18); }
    .tab-panels { display: block; }
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }
    .panel { overflow: hidden; }
    .panel-head { min-height: 64px; padding: 16px 17px; display: flex; align-items: center; justify-content: space-between; gap: 12px; border-bottom: 1px solid var(--line); }
    .panel-head h2 { margin: 0; font-size: 15px; }
    .panel-head span { color: var(--muted); font-size: 12px; }
    .button { border: 1px solid var(--line); border-radius: 10px; padding: 8px 11px; color: var(--text); background: rgba(255,255,255,.04); }
    .button:hover { border-color: rgba(185,255,102,.45); background: var(--accent-soft); }
    .button.primary { color: var(--active-ink); background: var(--accent); border-color: var(--accent); font-weight: 700; }
    .button.danger:hover { border-color: rgba(255,114,114,.55); background: rgba(255,114,114,.12); }
    .button.small { padding: 6px 8px; border-radius: 8px; font-size: 11px; }
    .subscriptions { padding: 12px; display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; }
    .subscription { padding: 14px; border-radius: 14px; border: 1px solid transparent; background: rgba(255,255,255,.025); }
    .subscription:hover { border-color: var(--line); }
    .subscription-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
    .subscription strong { font-size: 13px; }
    .subscription p { margin: 7px 0; color: var(--soft-text); font: 12px/1.5 ui-monospace, SFMono-Regular, monospace; overflow-wrap: anywhere; }
    .subscription-actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 11px; }
    .subscription-meta { margin-top: 7px; color: var(--muted); font: 11px/1.45 ui-monospace, SFMono-Regular, monospace; overflow-wrap: anywhere; }
    .chips { display: flex; flex-wrap: wrap; gap: 5px; }
    .chip { padding: 3px 7px; border-radius: 999px; font: 600 10px/1.4 ui-monospace, SFMono-Regular, monospace; color: var(--muted); background: rgba(255,255,255,.05); }
    .chip.webhook, .chip.event_queue, .chip.gateway_forward { color: var(--blue); background: rgba(119,184,255,.1); }
    .chip.api_cursor, .chip.poll, .chip.manual_backfill { color: var(--orange); background: rgba(255,184,107,.1); }
    .chip.push { color: var(--blue); background: rgba(119,184,255,.1); }
    .chip.pull { color: var(--orange); background: rgba(255,184,107,.1); }
    .platforms { padding: 12px; display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 10px; }
    .platform { padding: 14px; border-radius: 14px; background: rgba(255,255,255,.025); }
    .platform p { margin: 7px 0 9px; color: var(--soft-text); font: 12px/1.5 ui-monospace, SFMono-Regular, monospace; overflow-wrap: anywhere; }
    .action-chip { border: 0; text-align: left; }
    .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); }
    .dot.off { background: #555d6b; }
    .filters { display: grid; grid-template-columns: minmax(180px, .8fr) minmax(170px, .7fr) auto; gap: 8px; padding: 12px 14px; border-bottom: 1px solid var(--line); }
    .advanced-filters { display: grid; grid-template-columns: minmax(260px, 1.1fr) minmax(260px, 1fr) minmax(260px, 1fr) minmax(160px, .7fr) minmax(160px, .7fr); gap: 12px; padding: 14px; border-bottom: 1px solid var(--line); background: var(--glass); }
    .advanced-filters[hidden] { display: none; }
    .filter-group { min-width: 0; }
    .filter-title { margin-bottom: 7px; color: var(--muted); font-size: 12px; }
    .checkbox-grid { display: flex; flex-wrap: wrap; gap: 6px; max-height: 126px; overflow: auto; padding: 2px; }
    .check-chip { display: inline-flex; align-items: center; gap: 5px; min-height: 28px; padding: 5px 8px; border: 1px solid var(--line); border-radius: 999px; color: var(--soft-text); background: var(--glass); font: 600 10px/1.3 ui-monospace, SFMono-Regular, monospace; }
    .check-chip input { margin: 0; accent-color: var(--accent); }
    .advanced-note { color: var(--muted); font: 11px/1.4 ui-monospace, SFMono-Regular, monospace; }
    .control { width: 100%; height: 38px; border: 1px solid var(--line); border-radius: 10px; padding: 0 11px; color: var(--text); background: var(--control-bg); outline: none; }
    .control:focus { border-color: rgba(185,255,102,.55); box-shadow: 0 0 0 3px rgba(185,255,102,.08); }
    .event-head, .event-row { display: grid; grid-template-columns: 112px minmax(160px, .9fr) minmax(170px, .9fr) minmax(180px, 1.1fr) 145px 72px; gap: 14px; align-items: center; }
    .event-head { padding: 10px 15px; color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: .1em; border-bottom: 1px solid var(--line); }
    .event-list { max-height: 650px; overflow: auto; }
    .event-row { width: 100%; padding: 14px 15px; color: inherit; text-align: left; border: 0; border-bottom: 1px solid rgba(255,255,255,.055); background: transparent; }
    .event-row:hover { background: var(--row-hover); }
    .source { color: var(--accent); font: 700 12px ui-monospace, SFMono-Regular, monospace; }
    .kind, .target-label { font: 600 12px ui-monospace, SFMono-Regular, monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .target-label { color: var(--target-text); }
    .summary { color: var(--soft-text); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    time { color: var(--muted); font-size: 11px; }
    .count { text-align: right; font: 700 11px ui-monospace, SFMono-Regular, monospace; color: var(--muted); }
    .empty { padding: 54px 22px; text-align: center; color: var(--muted); }
    .empty strong { color: var(--text); display: block; margin-bottom: 7px; }
    .detail { position: fixed; inset: 0; z-index: 20; display: none; background: rgba(2,4,7,.66); backdrop-filter: blur(6px); }
    .detail.open { display: block; }
    .detail-panel { width: min(720px, 92vw); height: 100%; margin-left: auto; padding: 24px; overflow: auto; border-left: 1px solid var(--line); background: var(--detail-bg); box-shadow: -30px 0 80px rgba(0,0,0,.35); }
    .detail-top { display: flex; justify-content: space-between; align-items: center; gap: 14px; }
    .detail h2 { margin: 18px 0 6px; letter-spacing: -.03em; overflow-wrap: anywhere; }
    .detail-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px; margin: 18px 0; }
    .field { padding: 11px; border: 1px solid var(--line); border-radius: 11px; background: rgba(255,255,255,.025); }
    .field small { color: var(--muted); display: block; margin-bottom: 6px; }
    .field div { font: 12px/1.5 ui-monospace, SFMono-Regular, monospace; overflow-wrap: anywhere; }
    .json-title { display: flex; justify-content: space-between; align-items: center; margin: 18px 0 8px; }
    pre { margin: 0; padding: 14px; border: 1px solid var(--line); border-radius: 12px; color: var(--soft-text); background: var(--code-bg); overflow: auto; font: 11px/1.65 ui-monospace, SFMono-Regular, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
    dialog { width: min(540px, calc(100vw - 28px)); color: var(--text); border: 1px solid var(--line); border-radius: 18px; background: var(--dialog-bg); box-shadow: 0 40px 100px rgba(0,0,0,.55); }
    dialog::backdrop { background: rgba(0,0,0,.62); backdrop-filter: blur(5px); }
    dialog h2 { margin: 4px 0 18px; }
    .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    label { color: var(--muted); font-size: 12px; }
    label .control { margin-top: 6px; }
    .wide { grid-column: 1 / -1; }
    .checks { display: flex; gap: 16px; padding-top: 10px; }
    .checks label { color: var(--text); }
    .dialog-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 20px; }
    .dialog-note { margin: 0 0 14px; color: var(--muted); font-size: 12px; line-height: 1.6; }
    .token-preview { margin-top: 6px; font: 12px/1.5 ui-monospace, SFMono-Regular, monospace; letter-spacing: .02em; }
    .user-admin { margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--line); }
    .user-list { display: grid; gap: 7px; margin-top: 10px; }
    .user-row { display: grid; grid-template-columns: 1fr auto auto; gap: 8px; align-items: center; padding: 8px; border: 1px solid var(--line); border-radius: 10px; background: var(--glass); }
    .user-row span { overflow-wrap: anywhere; font: 11px/1.4 ui-monospace, SFMono-Regular, monospace; }
    .error { color: var(--danger); font-size: 12px; min-height: 18px; margin-top: 8px; }
    @media (max-width: 900px) {
      .stats { grid-template-columns: repeat(2, 1fr); }
      .tabs { display: flex; border-radius: 18px; }
      .tab { flex: 1 1 170px; justify-content: center; }
      .filters { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .advanced-filters { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .event-head { display: none; }
      .event-row { grid-template-columns: 90px 1fr 60px; }
      .event-row .target-label, .event-row .summary, .event-row time { display: none; }
    }
    @media (max-width: 580px) {
      .shell { padding: 18px 12px; }
      header { display: block; }
      .header-actions { justify-content: flex-start; margin-top: 14px; }
      .live { display: inline-flex; }
      .filters { grid-template-columns: 1fr; }
      .advanced-filters { grid-template-columns: 1fr; }
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
      <div class="header-actions">
        <a class="icon-link" id="githubLink" href="https://github.com/ChatArch/ChatEvent" target="_blank" rel="noreferrer" aria-label="Open GitHub repository">
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 .2a8 8 0 0 0-2.5 15.6c.4.1.5-.2.5-.4v-1.4c-2.2.5-2.7-.9-2.7-.9-.4-.9-.9-1.1-.9-1.1-.7-.5.1-.5.1-.5.8.1 1.2.8 1.2.8.7 1.2 1.9.9 2.3.7.1-.5.3-.9.5-1.1-1.8-.2-3.6-.9-3.6-3.9 0-.9.3-1.6.8-2.2-.1-.2-.4-1 .1-2.1 0 0 .7-.2 2.2.8A7.7 7.7 0 0 1 8 3.8c.7 0 1.4.1 2 .3 1.5-1 2.2-.8 2.2-.8.5 1.1.2 1.9.1 2.1.5.6.8 1.3.8 2.2 0 3-1.8 3.7-3.6 3.9.3.3.6.8.6 1.6v2.3c0 .2.1.5.6.4A8 8 0 0 0 8 .2Z"/></svg>
          GitHub
        </a>
        <a class="icon-link" id="docsLink" href="https://arch.gh.wzhecnu.cn/ChatEvent/" target="_blank" rel="noreferrer" aria-label="Open ChatEvent docs">
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 1.5A2.5 2.5 0 0 1 5.5 4v10.5A2.5 2.5 0 0 0 3 12H2V1.5h1Zm10 0h1V12h-1a2.5 2.5 0 0 0-2.5 2.5V4A2.5 2.5 0 0 1 13 1.5ZM5.5 2A1.5 1.5 0 0 0 4 3.5v7.3c.6.2 1.1.6 1.5 1.1V2Zm5 0v9.9c.4-.5.9-.9 1.5-1.1V3.5A1.5 1.5 0 0 0 10.5 2Z"/></svg>
          Docs
        </a>
        <button class="button theme-toggle" id="themeToggle" type="button" aria-pressed="false" aria-label="切换到日间模式">☾ 夜间</button>
        <div class="live" id="liveStatus">本地事件流 · 5 秒刷新</div>
      </div>
    </header>

    <section class="stats">
      <article class="card"><small>标准事件</small><span class="metric" id="eventCount">0</span></article>
      <article class="card"><small>启用订阅</small><span class="metric" id="subscriptionCount">0</span></article>
      <article class="card"><small>事件来源</small><span class="metric" id="sourceCount">0</span></article>
      <article class="card"><small>重复投递</small><span class="metric" id="duplicateCount">0</span><span class="metric-note">已去重</span></article>
    </section>

    <nav class="tabs" role="tablist" aria-label="Observatory sections">
      <button class="tab active" id="eventsTab" type="button" role="tab" aria-selected="true" aria-controls="eventsPanel" data-tab-target="eventsPanel">Event Stream <span class="tab-count" id="eventTabCount">0</span></button>
      <button class="tab" id="subscriptionsTab" type="button" role="tab" aria-selected="false" aria-controls="subscriptionsPanel" data-tab-target="subscriptionsPanel">Subscriptions <span class="tab-count" id="subscriptionTabCount">0</span></button>
      <button class="tab" id="platformsTab" type="button" role="tab" aria-selected="false" aria-controls="platformsPanel" data-tab-target="platformsPanel">Platform actions <span class="tab-count" id="platformTabCount">0</span></button>
    </nav>

    <section class="tab-panels">
      <section class="panel tab-panel active" id="eventsPanel" role="tabpanel" aria-labelledby="eventsTab">
        <div class="panel-head">
          <div><h2>Event stream</h2><span id="resultCount">0 条记录</span></div>
          <button class="button" id="refresh">刷新</button>
        </div>
        <div class="filters">
          <select class="control" id="sourceFilter"><option value="">全部来源</option></select>
          <select class="control" id="timeFilter">
            <option value="">全部时间</option>
            <option value="1">最近 24 小时</option>
            <option value="3">最近 3 天</option>
            <option value="7">最近 7 天</option>
            <option value="30">最近 30 天</option>
          </select>
          <button class="button" id="advancedFiltersToggle" type="button" aria-expanded="false" aria-controls="advancedFilters">高级选项 <span id="advancedFilterCount" class="tab-count">0</span></button>
        </div>
        <div class="advanced-filters" id="advancedFilters" hidden>
          <label>关键词搜索<input class="control" id="search" placeholder="payload、actor、conversation…" /></label>
          <div class="filter-group">
            <div class="filter-title">事件类型（随来源联动，可多选）</div>
            <div class="checkbox-grid" id="kindCheckboxes"></div>
            <div class="advanced-note" id="kindFilterHint">先选来源会收窄到该平台 action catalog。</div>
          </div>
          <div class="filter-group">
            <div class="filter-title">订阅 / 渠道（随来源联动，可多选）</div>
            <div class="checkbox-grid" id="subscriptionCheckboxes"></div>
          </div>
          <label>开始时间<input class="control" id="fromFilter" type="datetime-local" title="开始时间" /></label>
          <label>结束时间<input class="control" id="toFilter" type="datetime-local" title="结束时间" /></label>
        </div>
        <div class="event-head"><span>Source</span><span>Kind</span><span>Target</span><span>Summary</span><span>Captured</span><span>Seen</span></div>
        <div class="event-list" id="events"></div>
      </section>

      <section class="panel tab-panel" id="subscriptionsPanel" role="tabpanel" aria-labelledby="subscriptionsTab" hidden>
        <div class="panel-head">
          <div><h2>Subscriptions</h2><span>当前关注对象</span></div>
          <div class="subscription-actions">
            <span class="chip" id="sessionStatus">未登录</span>
            <button class="button" id="adminToken" type="button">账号 / API Token</button>
            <button class="button" id="addSubscription" type="button">＋ 新建</button>
          </div>
        </div>
        <div class="subscriptions" id="subscriptions"></div>
      </section>

      <section class="panel tab-panel" id="platformsPanel" role="tabpanel" aria-labelledby="platformsTab" hidden>
        <div class="panel-head">
          <div><h2>Platform actions</h2><span>v0.1 可控事件目录</span></div>
        </div>
        <div class="platforms" id="platforms"></div>
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
      <h2 id="subscriptionDialogTitle">新建订阅</h2>
      <div class="form-grid">
        <label>订阅 ID<input class="control" name="subscriptionId" placeholder="discourse-practice" /></label>
        <label>显示名称<input class="control" name="label" placeholder="核心仓库 Issues" /></label>
        <label>平台 source<select class="control" name="source" id="subscriptionSource" required><option value="">选择平台</option></select></label>
        <label>状态<select class="control" name="enabled"><option value="true">启用</option><option value="false">暂停</option></select></label>
        <label class="wide">关注目标<input class="control" name="target" required placeholder="repo:ChatArch/ChatEvent / stream:demo/topic:loop" /></label>
        <label>承载类型<input class="control" name="scopeType" id="subscriptionScopeType" placeholder="repo / pull_request / zulip_topic" /></label>
        <label>承载 Key<input class="control" name="scopeKey" id="subscriptionScopeKey" placeholder="ChatArch/ChatEvent / ChatArch/ChatEvent#4" /></label>
        <label>承载名称<input class="control" name="scopeDisplay" id="subscriptionScopeDisplay" placeholder="ChatArch/ChatEvent" /></label>
        <label>承载 URL<input class="control" name="scopeUrl" id="subscriptionScopeUrl" placeholder="https://..." /></label>
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

  <dialog id="adminTokenDialog">
    <div class="eyebrow">Account / API token</div>
    <h2>账号与 API Token</h2>
    <p class="dialog-note">网页端使用账号密码登录。API Token 用于 CLI、模型或程序代表你的账号调用 API；它不是主页登录凭据。生成后只展示一次，请复制保存。</p>
    <label class="wide">当前 API Token<input class="control token-preview" id="generatedAdminToken" placeholder="点击生成后显示 arch_xxx" autocomplete="off" spellcheck="false" /></label>
    <div class="error" id="adminTokenStatus"></div>
    <div class="dialog-actions">
      <button type="button" class="button primary" id="generateAdminToken">生成 / 轮换我的 Token</button>
      <button type="button" class="button" id="copyAdminToken">复制 Token</button>
      <button type="button" class="button" id="saveAdminToken">保存到当前浏览器</button>
      <button type="button" class="button" id="clearAdminToken">清除本地 Token</button>
      <button type="button" class="button" id="closeAdminToken">关闭</button>
    </div>
    <section class="user-admin" id="userAdminPanel">
      <div class="eyebrow">User management</div>
      <p class="dialog-note">管理员可以创建用户账号密码。用户登录后可生成自己的 API Token；管理员也可为用户轮换 Token。</p>
      <div class="form-grid">
        <label>用户名 / 邮箱<input class="control" id="newUserName" placeholder="user@example.com" autocomplete="off" /></label>
        <label>显示名称<input class="control" id="newUserDisplay" placeholder="Rex Wang" autocomplete="off" /></label>
        <label>初始密码<input class="control" id="newUserPassword" type="password" autocomplete="new-password" /></label>
        <label>角色<select class="control" id="newUserRole"><option value="member">member</option><option value="admin">admin</option></select></label>
        <button type="button" class="button primary" id="createUser">创建用户</button>
      </div>
      <div class="user-list" id="userList"></div>
    </section>
  </dialog>

  <dialog id="platformActionDialog">
    <div class="eyebrow">Platform action API</div>
    <h2 id="platformActionTitle">API 大致含义</h2>
    <div class="detail-grid" id="platformActionFields"></div>
    <div class="json-title"><strong>Action catalog JSON</strong></div><pre id="platformActionJson"></pre>
    <div class="dialog-actions"><button type="button" class="button" id="closePlatformAction">关闭</button></div>
  </dialog>

  <script>
    const state = { events: [], subscriptions: [], stats: {}, platforms: [], detail: null, editingSubscription: null, selectedKinds: new Set(), selectedSubscriptions: new Set() };
    const $ = (id) => document.getElementById(id);
    const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
    const formatTime = (value) => value ? new Intl.DateTimeFormat("zh-CN", {month:"2-digit", day:"2-digit", hour:"2-digit", minute:"2-digit", second:"2-digit"}).format(new Date(value)) : "—";
    const localDateTimeToIso = (value) => value ? new Date(value).toISOString() : "";
    function actionTargetLabel(target) {
      if (!target) return "—";
      const base = `${target.type}:${target.key}`;
      return target.display && target.display !== target.key ? `${base} · ${target.display}` : base;
    }
    function targetChain(target) {
      const chain = [];
      let current = target;
      while (current) { chain.push(actionTargetLabel(current)); current = current.parent; }
      return chain.reverse().join(" → ");
    }
    function actionLabel(event) {
      const action = event.action || {};
      return [action.kind || event.kind, action.object_type, action.verb].filter(Boolean).join(" · ");
    }
    function applyTheme(theme) {
      const normalized = theme === "light" ? "light" : "dark";
      document.documentElement.dataset.theme = normalized;
      localStorage.setItem("chateventTheme", normalized);
      $("themeToggle").setAttribute("aria-pressed", String(normalized === "light"));
      $("themeToggle").setAttribute("aria-label", normalized === "light" ? "切换到夜间模式" : "切换到日间模式");
      $("themeToggle").textContent = normalized === "light" ? "☀ 日间" : "☾ 夜间";
    }
    function toggleTheme() {
      applyTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light");
    }
    const api = async (path, options = {}) => {
      const headers = {"Content-Type": "application/json", ...(options.headers || {})};
      const response = await fetch(path, {...options, headers});
      if (!response.ok) {
        let detail = response.statusText;
        try { detail = (await response.json()).detail || detail; } catch (_error) {}
        const error = new Error(detail); error.status = response.status; throw error;
      }
      return response.json();
    };
    const getAdminToken = () => sessionStorage.getItem("chateventApiToken") || "";
    const adminAuthHeaders = (token = getAdminToken()) => token ? {"X-ChatEvent-Admin-Token": token} : {};
    function setAdminToken(value) {
      if (value) sessionStorage.setItem("chateventApiToken", value);
      else sessionStorage.removeItem("chateventApiToken");
    }
    function openAdminTokenDialog({message = ""} = {}) {
      const input = $("generatedAdminToken");
      input.value = getAdminToken();
      $("adminTokenStatus").textContent = message;
      $("adminTokenDialog").showModal();
      input.focus();
      input.select();
      loadUsers();
    }
    async function copyAdminToken() {
      const input = $("generatedAdminToken");
      if (!input.value.trim()) {
        $("adminTokenStatus").textContent = "请先生成或粘贴 API Token。";
        return;
      }
      input.select();
      try {
        await navigator.clipboard.writeText(input.value.trim());
      } catch (_error) {
        document.execCommand("copy");
      }
      $("adminTokenStatus").textContent = "已复制 API Token；CLI/模型可用它作为 X-ChatEvent-Admin-Token。";
    }
    function renderSessionStatus(session) {
      const status = $("sessionStatus");
      if (!session?.admin_required) {
        status.textContent = "本地免登录";
        return;
      }
      if (session.authenticated && session.user) {
        status.textContent = `${session.user.role}:${session.user.username}`;
        return;
      }
      status.textContent = "未登录";
    }
    async function logoutAdminToken() {
      const session = await api("/api/logout", {method: "POST"});
      renderSessionStatus(session);
      return session;
    }
    async function generateMyApiToken() {
      const result = await api("/api/me/token", {method: "POST"});
      $("generatedAdminToken").value = result.token;
      setAdminToken(result.token);
      $("adminTokenStatus").textContent = "已生成并保存你的 API Token；它只展示一次，请复制保存。";
      await copyAdminToken();
    }
    function renderUsers(users) {
      const root = $("userList");
      if (!users.length) {
        root.innerHTML = `<span class="advanced-note">暂无用户；管理员可以创建 member/admin 账号。</span>`;
        return;
      }
      root.innerHTML = users.map(user => `
        <div class="user-row">
          <span>${escapeHtml(user.username)} · ${escapeHtml(user.role)}${user.enabled ? "" : " · disabled"}</span>
          <span>${escapeHtml(user.display_name || "")}</span>
          <button class="button small" type="button" data-token-user="${escapeHtml(user.id)}">生成 Token</button>
          <button class="button small danger" type="button" data-delete-user="${escapeHtml(user.id)}">删除</button>
        </div>
      `).join("");
      root.querySelectorAll("[data-token-user]").forEach(button => button.addEventListener("click", async () => {
        const result = await adminApi(`/api/users/${encodeURIComponent(button.dataset.tokenUser)}/token`, {method: "POST"});
        $("generatedAdminToken").value = result.token;
        $("adminTokenStatus").textContent = `已为 ${result.user.username} 生成 API Token，只展示一次。`;
        await copyAdminToken();
      }));
      root.querySelectorAll("[data-delete-user]").forEach(button => button.addEventListener("click", async () => {
        await adminApi(`/api/users/${encodeURIComponent(button.dataset.deleteUser)}`, {method: "DELETE"});
        await loadUsers();
      }));
    }
    async function loadUsers() {
      try {
        const users = await api("/api/users");
        renderUsers(users);
      } catch (_error) {
        $("userList").innerHTML = `<span class="advanced-note">管理员登录后可查看和创建用户。</span>`;
      }
    }
    async function createManagedUser() {
      const username = $("newUserName").value.trim();
      const password = $("newUserPassword").value;
      if (!username || !password) {
        $("adminTokenStatus").textContent = "请输入用户名/邮箱和初始密码。";
        return;
      }
      const result = await adminApi("/api/users", {
        method: "POST",
        body: JSON.stringify({
          username,
          password,
          display_name: $("newUserDisplay").value.trim() || null,
          role: $("newUserRole").value,
        }),
      });
      $("adminTokenStatus").textContent = `已创建 ${result.user.username}；用户可用账号密码登录，并自行生成 API Token。`;
      $("newUserName").value = "";
      $("newUserDisplay").value = "";
      $("newUserPassword").value = "";
      await loadUsers();
    }
    async function adminApi(path, options = {}, retry = true) {
      const token = getAdminToken();
      const headers = {...(options.headers || {})};
      if (token) headers["X-ChatEvent-Admin-Token"] = token;
      try { return await api(path, {...options, headers}); }
      catch (error) {
        if (error.status === 401 && retry) {
          openAdminTokenDialog({message: "需要登录或 API Token 才能完成这个操作；请先登录，或在账号面板生成/保存 Token。"});
          throw error;
        }
        throw error;
      }
    }

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
    }

    function updateOptions(id, label, values) {
      const select = $(id); const current = select.value;
      select.innerHTML = `<option value="">${escapeHtml(label)}</option>` + values.map(value => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("");
      select.value = values.includes(current) ? current : "";
    }

    function selectedSource() { return $("sourceFilter").value; }

    function actionKindsForSource() {
      const source = selectedSource();
      const platforms = source ? state.platforms.filter(platform => platform.id === source) : state.platforms;
      const catalogKinds = platforms.flatMap(platform => (platform.actions || []).map(action => action.kind));
      const observedKinds = state.events
        .map(item => item.event)
        .filter(event => !source || event.source === source)
        .map(event => event.kind);
      const fallbackKinds = source ? [] : Object.keys(state.stats.kinds || {});
      const kinds = [...catalogKinds, ...observedKinds, ...fallbackKinds];
      return Array.from(new Set(kinds)).sort();
    }

    function subscriptionsForSource() {
      const source = selectedSource();
      return state.subscriptions.filter(item => !source || item.source === source);
    }

    function pruneSelection(selection, allowed) {
      const allowedSet = new Set(allowed);
      Array.from(selection).forEach(value => { if (!allowedSet.has(value)) selection.delete(value); });
    }

    function renderCheckboxes(rootId, values, selected, name, emptyText) {
      const root = $(rootId);
      if (!values.length) {
        root.innerHTML = `<span class="advanced-note">${escapeHtml(emptyText)}</span>`;
        return;
      }
      root.innerHTML = values.map(value => `
        <label class="check-chip"><input type="checkbox" name="${escapeHtml(name)}" value="${escapeHtml(value)}" ${selected.has(value) ? "checked" : ""} />${escapeHtml(value)}</label>
      `).join("");
    }

    function updateAdvancedCount() {
      const count = state.selectedKinds.size + state.selectedSubscriptions.size + ($("search").value.trim() ? 1 : 0) + ($("fromFilter").value ? 1 : 0) + ($("toFilter").value ? 1 : 0);
      $("advancedFilterCount").textContent = String(count);
    }

    function renderAdvancedFilters() {
      const kinds = actionKindsForSource();
      const subscriptions = subscriptionsForSource();
      const subscriptionIds = subscriptions.map(item => item.id).sort();
      pruneSelection(state.selectedKinds, kinds);
      pruneSelection(state.selectedSubscriptions, subscriptionIds);
      renderCheckboxes("kindCheckboxes", kinds, state.selectedKinds, "kindOption", "当前来源还没有可选 action。/api/platforms 会补全目录。 ");
      renderCheckboxes("subscriptionCheckboxes", subscriptionIds, state.selectedSubscriptions, "subscriptionOption", "当前来源还没有订阅。 ");
      const sourceText = selectedSource() || "全部来源";
      $("kindFilterHint").textContent = `事件类型来自 ${sourceText} 的 platform action catalog；多选时在前端二次过滤。`;
      updateAdvancedCount();
    }

    function applyAdvancedEventFilters(items) {
      return items.filter(item => {
        const event = item.event;
        if (state.selectedKinds.size && !state.selectedKinds.has(event.kind)) return false;
        if (state.selectedSubscriptions.size && !state.selectedSubscriptions.has(event.subscription_id || "")) return false;
        return true;
      });
    }

    function renderSubscriptions(items) {
      state.subscriptions = items;
      $("subscriptionTabCount").textContent = items.length;
      const root = $("subscriptions");
      if (!items.length) {
        root.innerHTML = `<div class="empty"><strong>还没有订阅</strong>先记录要关注的平台与对象。</div>`;
        return;
      }
      root.innerHTML = items.map((item, index) => {
        const scopeText = targetChain(item.scope) || item.target;
        const actionText = (item.actions || []).map(action => action.kind).join(", ") || item.event_kinds.join(", ");
        return `
        <article class="subscription">
          <div class="subscription-top"><strong>${escapeHtml(item.label || item.source)}</strong><span class="dot ${item.enabled ? "" : "off"}"></span></div>
          <p>${escapeHtml(item.target)}</p>
          <div class="subscription-meta">scope: ${escapeHtml(scopeText)}</div>
          <div class="subscription-meta">actions: ${escapeHtml(actionText)}</div>
          <div class="subscription-meta">id: ${escapeHtml(item.id)}${item.last_cursor ? ` · cursor: ${escapeHtml(item.last_cursor)}` : ""}</div>
          <div class="chips">
            <span class="chip">${escapeHtml(item.source)}</span>
            ${item.capture_modes.map(mode => `<span class="chip ${escapeHtml(mode)}">${escapeHtml(mode)}</span>`).join("")}
            <span class="chip">${escapeHtml(item.event_kinds.join(", "))}</span>
          </div>
          <div class="subscription-actions">
            <button class="button small" type="button" data-action="edit-subscription" data-index="${index}">编辑</button>
            <button class="button small" type="button" data-action="toggle-subscription" data-index="${index}">${item.enabled ? "暂停" : "启用"}</button>
            <button class="button small danger" type="button" data-action="delete-subscription" data-index="${index}">删除</button>
          </div>
        </article>`;
      }).join("");
      root.querySelectorAll('[data-action="edit-subscription"]').forEach(button => button.addEventListener("click", () => editSubscription(Number(button.dataset.index))));
      root.querySelectorAll('[data-action="toggle-subscription"]').forEach(button => button.addEventListener("click", () => toggleSubscription(Number(button.dataset.index))));
      root.querySelectorAll('[data-action="delete-subscription"]').forEach(button => button.addEventListener("click", () => deleteSubscription(Number(button.dataset.index))));
    }

    function renderPlatforms(platforms) {
      state.platforms = platforms;
      $("platformTabCount").textContent = platforms.length;
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
            ${platform.actions.slice(0, 12).map(action => `<button class="chip action-chip" type="button" data-platform="${escapeHtml(platform.id)}" data-action-kind="${escapeHtml(action.kind)}" title="${escapeHtml(action.description)} · target: ${escapeHtml((action.target_types || []).join(' / '))}">${escapeHtml(action.kind)} → ${escapeHtml((action.target_types || []).slice(0, 2).join('/'))}</button>`).join("")}
          </div>
        </article>`).join("");
      root.querySelectorAll(".action-chip").forEach(button => button.addEventListener("click", () => openPlatformAction(button.dataset.platform, button.dataset.actionKind)));
      const source = $("subscriptionSource");
      const current = source.value;
      source.innerHTML = `<option value="">选择平台</option>` + platforms.map(platform => `<option value="${escapeHtml(platform.id)}">${escapeHtml(platform.display_name)} · ${escapeHtml(platform.id)}</option>`).join("");
      source.value = platforms.some(platform => platform.id === current) ? current : "";
    }

    function openPlatformAction(platformId, actionKind) {
      const platform = state.platforms.find(item => item.id === platformId);
      const action = platform?.actions?.find(item => item.kind === actionKind);
      if (!platform || !action) return;
      $("platformActionTitle").textContent = `${platform.display_name} · ${action.kind}`;
      const modes = action.acquisition_modes || [];
      const webhookEvents = action.webhook_events?.length ? action.webhook_events.join(", ") : "—";
      const apiMeaning = `${action.description} 捕获后会规范化为 kind=${action.kind}，target 通常挂在 ${(action.target_types || []).join(" / ") || action.object_type} 上；api_cursor 模式只用于官方 API 增量补偿或对象补全。`;
      $("platformActionFields").innerHTML = [
        field("平台", `${platform.display_name} (${platform.id})`),
        field("Action kind", action.kind),
        field("对象 / 动词", `${action.object_type} · ${action.action}`),
        field("Target types", (action.target_types || []).join(" → ")),
        field("捕获方式", modes.join(", ")),
        field("Webhook events", webhookEvents),
        field("API 大致含义", apiMeaning),
        field("Scope examples", (platform.scope_examples || []).join(" / ")),
      ].join("");
      $("platformActionJson").textContent = JSON.stringify(action, null, 2);
      $("platformActionDialog").showModal();
    }

    function renderEvents(items) {
      state.events = items;
      $("eventTabCount").textContent = items.length;
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
          <span class="target-label" title="${escapeHtml(targetChain(event.target))}">${escapeHtml(actionTargetLabel(event.target))}</span>
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
        field("Action", actionLabel(event)),
        field("Action target", actionTargetLabel(event.target)),
        field("Target chain", targetChain(event.target)),
        field("Conversation", event.conversation_id),
        field("Actor", event.actor?.display || event.actor_id),
        field("Actor role", event.actor?.role || event.actor_role),
        field("Subject", [event.subject_type, event.subject_id].filter(Boolean).join(":")),
        field("Cursor", event.cursor),
        field("URL", event.url),
      ].join("");
      $("normalizedJson").textContent = JSON.stringify(event.payload || {}, null, 2);
      $("rawJson").textContent = JSON.stringify(event.raw_payload ?? {}, null, 2);
      $("detail").classList.add("open"); $("detail").setAttribute("aria-hidden", "false");
    }

    function closeDetail() { $("detail").classList.remove("open"); $("detail").setAttribute("aria-hidden", "true"); }

    function activateTab(targetId) {
      document.querySelectorAll(".tab").forEach(tab => {
        const active = tab.dataset.tabTarget === targetId;
        tab.classList.toggle("active", active);
        tab.setAttribute("aria-selected", String(active));
      });
      document.querySelectorAll(".tab-panel").forEach(panel => {
        const active = panel.id === targetId;
        panel.classList.toggle("active", active);
        panel.hidden = !active;
      });
    }

    function openSubscriptionDialog(item = null) {
      state.editingSubscription = item;
      const form = $("subscriptionForm");
      form.reset();
      $("subscriptionDialogTitle").textContent = item ? "编辑订阅" : "新建订阅";
      form.elements.subscriptionId.value = item?.id || "";
      form.elements.subscriptionId.readOnly = Boolean(item);
      form.elements.label.value = item?.label || "";
      form.elements.source.value = item?.source || "";
      form.elements.enabled.value = item?.enabled === false ? "false" : "true";
      form.elements.target.value = item?.target || "";
      form.elements.scopeType.value = item?.scope?.type || "";
      form.elements.scopeKey.value = item?.scope?.key || "";
      form.elements.scopeDisplay.value = item?.scope?.display || "";
      form.elements.scopeUrl.value = item?.scope?.url || "";
      form.elements.eventKinds.value = (item?.event_kinds || ["*"]).join(", " );
      form.querySelectorAll('input[name="mode"]').forEach(input => { input.checked = (item?.capture_modes || ["webhook"]).includes(input.value); });
      $("formError").textContent = "";
      dialog.showModal();
    }

    function subscriptionBodyFromForm(formElement) {
      const form = new FormData(formElement);
      const captureModes = Array.from(formElement.querySelectorAll('input[name="mode"]:checked')).map(input => input.value);
      if (!captureModes.length) throw new Error("至少选择一种捕获方式。");
      const base = state.editingSubscription ? {...state.editingSubscription} : {};
      const id = String(form.get("subscriptionId") || "").trim();
      const body = {
        ...base,
        label: form.get("label") || null,
        source: form.get("source"),
        target: form.get("target"),
        enabled: form.get("enabled") !== "false",
        event_kinds: String(form.get("eventKinds") || "*").split(",").map(value => value.trim()).filter(Boolean),
        capture_modes: captureModes,
      };
      if (id) body.id = id; else delete body.id;
      delete body.actions;
      const scopeType = String(form.get("scopeType") || "").trim();
      const scopeKey = String(form.get("scopeKey") || "").trim();
      if (scopeType && scopeKey) {
        body.scope = {
          ...(base.scope || {}),
          type: scopeType,
          key: scopeKey,
          display: String(form.get("scopeDisplay") || "").trim() || null,
          url: String(form.get("scopeUrl") || "").trim() || null,
        };
      } else {
        delete body.scope;
      }
      return body;
    }

    function editSubscription(index) { openSubscriptionDialog(state.subscriptions[index]); }

    async function toggleSubscription(index) {
      const item = state.subscriptions[index];
      if (!item) return;
      await adminApi("/api/subscriptions", {method: "POST", body: JSON.stringify({...item, enabled: !item.enabled})});
      await loadAll();
    }

    async function deleteSubscription(index) {
      const item = state.subscriptions[index];
      if (!item || !window.confirm(`删除订阅 ${item.id}？这不会删除已捕获事件。`)) return;
      await adminApi(`/api/subscriptions/${encodeURIComponent(item.id)}`, {method: "DELETE"});
      await loadAll();
    }

    async function loadAll() {
      try {
        const params = new URLSearchParams();
        if ($("sourceFilter").value) params.set("source", $("sourceFilter").value);
        if (state.selectedKinds.size === 1) params.set("kind", Array.from(state.selectedKinds)[0]);
        if (state.selectedSubscriptions.size === 1) params.set("subscription_id", Array.from(state.selectedSubscriptions)[0]);
        if ($("timeFilter").value) params.set("days", $("timeFilter").value);
        if ($("fromFilter").value) params.set("from", localDateTimeToIso($("fromFilter").value));
        if ($("toFilter").value) params.set("to", localDateTimeToIso($("toFilter").value));
        if ($("search").value.trim()) params.set("q", $("search").value.trim());
        const [stats, subscriptions, events, platforms, session] = await Promise.all([
          api("/api/stats"),
          api("/api/subscriptions", {headers: adminAuthHeaders()}),
          api(`/api/events?${params}`),
          api("/api/platforms"),
          api("/api/session", {headers: adminAuthHeaders()}),
        ]);
        state.stats = stats;
        renderSessionStatus(session);
        renderStats(stats); renderSubscriptions(subscriptions); renderPlatforms(platforms.items); renderAdvancedFilters(); renderEvents(applyAdvancedEventFilters(events.items));
        $("liveStatus").textContent = `本地事件流 · ${formatTime(stats.latest_captured_at)}`;
      } catch (error) {
        $("liveStatus").textContent = `连接失败 · ${error.message}`;
      }
    }

    let debounce;
    const debouncedLoad = () => { clearTimeout(debounce); debounce = setTimeout(loadAll, 260); };
    document.querySelectorAll(".tab").forEach(tab => tab.addEventListener("click", () => activateTab(tab.dataset.tabTarget)));
    $("search").addEventListener("input", () => { updateAdvancedCount(); debouncedLoad(); });
    $("sourceFilter").addEventListener("change", () => { state.selectedKinds.clear(); state.selectedSubscriptions.clear(); loadAll(); });
    $("timeFilter").addEventListener("change", loadAll);
    $("fromFilter").addEventListener("change", () => { updateAdvancedCount(); loadAll(); });
    $("toFilter").addEventListener("change", () => { updateAdvancedCount(); loadAll(); });
    $("advancedFiltersToggle").addEventListener("click", () => {
      const panel = $("advancedFilters");
      const next = panel.hidden;
      panel.hidden = !next;
      $("advancedFiltersToggle").setAttribute("aria-expanded", String(next));
    });
    $("kindCheckboxes").addEventListener("change", event => {
      const input = event.target;
      if (!input || input.name !== "kindOption") return;
      input.checked ? state.selectedKinds.add(input.value) : state.selectedKinds.delete(input.value);
      updateAdvancedCount(); loadAll();
    });
    $("subscriptionCheckboxes").addEventListener("change", event => {
      const input = event.target;
      if (!input || input.name !== "subscriptionOption") return;
      input.checked ? state.selectedSubscriptions.add(input.value) : state.selectedSubscriptions.delete(input.value);
      updateAdvancedCount(); loadAll();
    });
    $("themeToggle").addEventListener("click", toggleTheme);
    $("refresh").addEventListener("click", loadAll);
    $("closeDetail").addEventListener("click", closeDetail);
    $("detail").addEventListener("click", event => { if (event.target === $("detail")) closeDetail(); });
    $("copyRaw").addEventListener("click", async () => navigator.clipboard.writeText($("rawJson").textContent));
    $("closePlatformAction").addEventListener("click", () => $("platformActionDialog").close());

    const dialog = $("subscriptionDialog");
    $("adminToken").addEventListener("click", () => openAdminTokenDialog());
    $("generateAdminToken").addEventListener("click", async () => {
      try { await generateMyApiToken(); }
      catch (error) { $("adminTokenStatus").textContent = `生成 Token 失败：${error.message}`; }
    });
    $("copyAdminToken").addEventListener("click", copyAdminToken);
    $("createUser").addEventListener("click", async () => {
      try { await createManagedUser(); }
      catch (error) { $("adminTokenStatus").textContent = `创建用户失败：${error.message}`; }
    });
    $("saveAdminToken").addEventListener("click", () => {
      const token = $("generatedAdminToken").value.trim();
      if (token && !token.startsWith("arch_")) {
        $("adminTokenStatus").textContent = "API Token 应使用 arch_xxx 格式。";
        return;
      }
      setAdminToken(token);
      $("adminTokenStatus").textContent = token ? "已保存到当前浏览器，后续编辑会带上这个 API Token。" : "已清空当前浏览器保存的 API Token。";
    });
    $("clearAdminToken").addEventListener("click", () => {
      setAdminToken("");
      $("generatedAdminToken").value = "";
      $("adminTokenStatus").textContent = "已清空当前浏览器保存的 API Token。";
    });
    $("closeAdminToken").addEventListener("click", () => $("adminTokenDialog").close());
    $("addSubscription").addEventListener("click", () => openSubscriptionDialog());
    $("cancelSubscription").addEventListener("click", () => dialog.close());
    $("subscriptionForm").addEventListener("submit", async event => {
      event.preventDefault(); $("formError").textContent = "";
      const formElement = event.currentTarget;
      try {
        const body = subscriptionBodyFromForm(formElement);
        await adminApi("/api/subscriptions", {method: "POST", body: JSON.stringify(body)});
        formElement.reset(); state.editingSubscription = null; dialog.close(); await loadAll();
      } catch (error) { $("formError").textContent = error.message; }
    });

    applyTheme(localStorage.getItem("chateventTheme") || "dark");
    loadAll(); setInterval(loadAll, 5000);
  </script>
</body>
</html>"""
