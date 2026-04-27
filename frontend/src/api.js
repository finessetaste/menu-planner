const BASE = "/api";

async function req(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(`${BASE}${path}`, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Error");
  }
  return res.json();
}

// ── Recipes ───────────────────────────────────────────────────────────────────
export const api = {
  recipes: {
    list: (tipo, subtipo) => {
      const p = new URLSearchParams();
      if (tipo) p.set("tipo", tipo);
      if (subtipo) p.set("subtipo", subtipo);
      return req("GET", `/recipes/?${p}`);
    },
    get:   (id)        => req("GET",    `/recipes/${id}`),
    patch: (id, data)  => req("PATCH",  `/recipes/${id}`, data),
    del:   (id)        => req("DELETE", `/recipes/${id}`),
    patchIngredient: (rid, iid, data) =>
      req("PATCH", `/recipes/${rid}/ingredients/${iid}`, data),
  },

  pdf: {
    upload: async (file) => {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${BASE}/pdf/upload`, { method: "POST", body: fd });
      if (!res.ok) throw new Error((await res.json()).detail);
      return res.json();
    },
    status: () => req("GET", "/pdf/status"),
  },

  weeklyPlan: {
    get:      (weekStart) => req("GET",   `/weekly-plan/?week_start=${weekStart || ""}`),
    patchDay: (id, data)  => req("PATCH", `/weekly-plan/${id}`, data),
    patchSlot:(id, data)  => req("PATCH", `/weekly-plan/slot/${id}`, data),
  },

  shopping: {
    list:     (ws) => req("GET",    `/shopping/?week_start=${ws || ""}`),
    generate: (ws) => req("POST",   `/shopping/generate?week_start=${ws || ""}`),
    add:      (ws, item) => req("POST", `/shopping/?week_start=${ws || ""}`, item),
    patch:    (id, data) => req("PATCH", `/shopping/${id}`, data),
    del:      (id)       => req("DELETE",`/shopping/${id}`),
    clearChecked: (ws)   => req("DELETE",`/shopping/?week_start=${ws || ""}`),
  },

  config: {
    get: ()      => req("GET", "/config/"),
    set: (data)  => req("PUT", "/config/", data),
  },

  girlsDinners: {
    status:      ()              => req("GET", "/girls-dinners/status"),
    suggestions: (ws)            => req("GET", `/girls-dinners/suggestions?week_start=${ws || ""}`),
    select:      (girl, day, desc) =>
      req("PUT", `/girls-dinners/select?girl=${girl}&day=${day}&dinner_description=${encodeURIComponent(desc)}`),
    getConfig:   ()              => req("GET", "/girls-dinners/config"),
    setConfig:   (data)          => req("PUT", "/girls-dinners/config", data),
  },
};
