import json
import subprocess
import textwrap

from chatevent.dashboard import DASHBOARD_HTML


def run_dashboard_script(assertion: str) -> dict:
    script = DASHBOARD_HTML.split("<script>", 1)[1].split("</script>", 1)[0]
    script = script.replace(
        'applyTheme(localStorage.getItem("chateventTheme") || "dark");\n    loadAll(); setInterval(loadAll, 5000);',
        'globalThis.__chateventTest = {api, adminApi, refreshSessionCsrf, logoutAdminToken, state, getAdminToken, setAdminToken};',
    )
    harness = f"""
    const vm = require("node:vm");
    const elements = new Map();
    function makeElement(id) {{
      return {{
        id,
        value: "",
        textContent: "",
        innerHTML: "",
        hidden: false,
        dataset: {{}},
        style: {{}},
        classList: {{ add() {{}}, remove() {{}}, toggle() {{}} }},
        setAttribute() {{}},
        addEventListener() {{}},
        querySelectorAll() {{ return []; }},
        querySelector() {{ return null; }},
        showModal() {{}},
        close() {{}},
        focus() {{}},
        select() {{}},
        reset() {{}},
      }};
    }}
    const context = {{
      console,
      setTimeout,
      clearTimeout,
      setInterval() {{ return 0; }},
      document: {{
        documentElement: {{ dataset: {{}} }},
        getElementById(id) {{
          if (!elements.has(id)) elements.set(id, makeElement(id));
          return elements.get(id);
        }},
        querySelectorAll() {{ return []; }},
        execCommand() {{ return true; }},
      }},
      localStorage: {{
        data: {{}},
        getItem(key) {{ return this.data[key] || ""; }},
        setItem(key, value) {{ this.data[key] = String(value); }},
        removeItem(key) {{ delete this.data[key]; }},
      }},
      sessionStorage: {{
        data: {{}},
        getItem(key) {{ return this.data[key] || ""; }},
        setItem(key, value) {{ this.data[key] = String(value); }},
        removeItem(key) {{ delete this.data[key]; }},
      }},
      navigator: {{ clipboard: {{ async writeText() {{}} }} }},
      Intl,
      Date,
      URLSearchParams,
      encodeURIComponent,
    }};
    vm.createContext(context);
    vm.runInContext({json.dumps(script)}, context);
    (async () => {{
      {assertion}
    }})().then(
      (result) => process.stdout.write(JSON.stringify(result)),
      (error) => {{
        console.error(error && error.stack || error);
        process.exit(1);
      }},
    );
    """
    result = subprocess.run(
        ["node", "-e", textwrap.dedent(harness)],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return json.loads(result.stdout)


def test_cached_stale_token_does_not_block_cookie_csrf_for_writes() -> None:
    result = run_dashboard_script(
        """
        const captured = [];
        context.sessionStorage.setItem("chateventApiToken", "stale-token");
        context.fetch = async (path, options = {}) => {
          captured.push({path, method: options.method || "GET", headers: options.headers || {}});
          if (path === "/api/session") {
            return {ok: true, json: async () => ({authenticated: true, csrf_token: "cookie-csrf"})};
          }
          return {ok: true, json: async () => ({ok: true})};
        };
        await context.__chateventTest.refreshSessionCsrf();
        await context.__chateventTest.api("/api/subscriptions", {method: "POST", body: "{}"});
        return {csrf: context.__chateventTest.state.csrf, captured};
        """
    )

    assert result["csrf"] == "cookie-csrf"
    assert [call["path"] for call in result["captured"]] == [
        "/api/session",
        "/api/subscriptions",
    ]
    write_headers = result["captured"][1]["headers"]
    assert write_headers["X-ChatEvent-Admin-Token"] == "stale-token"
    assert write_headers["X-CSRF-Token"] == "cookie-csrf"


def test_admin_api_initializes_cookie_csrf_with_cached_stale_token() -> None:
    result = run_dashboard_script(
        """
        const captured = [];
        context.sessionStorage.setItem("chateventApiToken", "stale-token");
        context.fetch = async (path, options = {}) => {
          captured.push({path, method: options.method || "GET", headers: options.headers || {}});
          if (path === "/api/session") {
            return {ok: true, json: async () => ({authenticated: true, csrf_token: "cookie-csrf"})};
          }
          return {ok: true, json: async () => ({ok: true})};
        };
        await context.__chateventTest.adminApi("/api/subscriptions", {method: "POST", body: "{}"});
        return {csrf: context.__chateventTest.state.csrf, captured};
        """
    )

    assert result["csrf"] == "cookie-csrf"
    assert [call["path"] for call in result["captured"]] == [
        "/api/session",
        "/api/subscriptions",
    ]
    write_headers = result["captured"][1]["headers"]
    assert write_headers["X-ChatEvent-Admin-Token"] == "stale-token"
    assert write_headers["X-CSRF-Token"] == "cookie-csrf"


def test_admin_api_valid_token_write_stays_bounded_without_cookie_csrf() -> None:
    result = run_dashboard_script(
        """
        const captured = [];
        context.sessionStorage.setItem("chateventApiToken", "valid-token");
        context.fetch = async (path, options = {}) => {
          captured.push({path, method: options.method || "GET", headers: options.headers || {}});
          if (path === "/api/session") {
            return {ok: true, json: async () => ({authenticated: false})};
          }
          return {ok: true, json: async () => ({ok: true})};
        };
        await context.__chateventTest.adminApi("/api/subscriptions", {method: "POST", body: "{}"});
        return {csrf: context.__chateventTest.state.csrf, captured};
        """
    )

    assert result["csrf"] == ""
    assert [call["path"] for call in result["captured"]] == [
        "/api/session",
        "/api/subscriptions",
    ]
    write_headers = result["captured"][1]["headers"]
    assert write_headers["X-ChatEvent-Admin-Token"] == "valid-token"
    assert "X-CSRF-Token" not in write_headers


def test_cookie_logout_carries_csrf_even_when_cached_token_exists() -> None:
    result = run_dashboard_script(
        """
        const captured = [];
        context.sessionStorage.setItem("chateventApiToken", "stale-token");
        context.__chateventTest.state.csrf = "cookie-csrf";
        context.fetch = async (path, options = {}) => {
          captured.push({path, method: options.method || "GET", headers: options.headers || {}});
          return {ok: true, json: async () => ({authenticated: false})};
        };
        await context.__chateventTest.logoutAdminToken();
        return {captured};
        """
    )

    assert [call["path"] for call in result["captured"]] == ["/api/logout"]
    headers = result["captured"][0]["headers"]
    assert headers["X-ChatEvent-Admin-Token"] == "stale-token"
    assert headers["X-CSRF-Token"] == "cookie-csrf"
