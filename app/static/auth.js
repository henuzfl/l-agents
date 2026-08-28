"use strict";
(() => {
  const originalFetch = window.fetch.bind(window);
  let accessToken = "";
  let refreshPromise = null;
  async function refreshAccess() {
    if (refreshPromise) return refreshPromise;
    refreshPromise = originalFetch("/api/v1/auth/refresh", {method:"POST",credentials:"same-origin"}).then(async response => {
      if (!response.ok) throw new Error("unauthenticated");
      accessToken = (await response.json()).access_token;
      const me = await originalFetch("/api/v1/auth/me", {headers:{Authorization:`Bearer ${accessToken}`}});
      if (!me.ok) throw new Error("unauthenticated");
      return me.json();
    }).finally(() => { refreshPromise = null; });
    return refreshPromise;
  }
  function redirectToLogin() { accessToken = ""; if (location.pathname !== "/login") location.replace("/login"); }
  window.authReady = refreshAccess().catch(() => { redirectToLogin(); return null; });
  window.fetch = async (input, init = {}) => {
    const url = typeof input === "string" ? input : input.url;
    if (!url.startsWith("/api/v1/") || url.startsWith("/api/v1/auth/")) return originalFetch(input, init);
    if (!await window.authReady) return new Response(null, {status:401});
    const headers = new Headers(init.headers || (input instanceof Request ? input.headers : {}));
    headers.set("Authorization", `Bearer ${accessToken}`);
    let response = await originalFetch(input, {...init, headers});
    if (response.status !== 401) return response;
    try { await refreshAccess(); headers.set("Authorization", `Bearer ${accessToken}`); response = await originalFetch(input, {...init, headers}); } catch { /* redirect below */ }
    if (response.status === 401) redirectToLogin();
    return response;
  };
  window.logout = async () => { await originalFetch("/api/v1/auth/logout", {method:"POST",credentials:"same-origin"}); redirectToLogin(); };
})();
