/* Adds the X-DeskMon header to every write request to Mondesk's own API.
   The server rejects writes without it, which blocks other websites (they can't add a
   custom header to a request to 127.0.0.1 without a CORS preflight the server never allows). */
(() => {
  const original = window.fetch;
  window.fetch = (input, init = {}) => {
    const url = new URL(typeof input === "string" ? input : input.url, location.href);
    const method = (init.method || (typeof input === "object" && input.method) || "GET").toUpperCase();
    if (url.origin === location.origin && url.pathname.startsWith("/api/") && method !== "GET") {
      const headers = new Headers(init.headers || (typeof input === "object" ? input.headers : undefined));
      headers.set("X-DeskMon", "1");
      init = { ...init, headers };
    }
    return original(input, init);
  };
})();
