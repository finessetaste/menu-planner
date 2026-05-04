import { useState, useEffect, useRef } from "react";
import { api } from "../api";

const TIPOS = ["desayuno", "comida", "comida_cena", "cena", "snack"];
const TIPO_LABELS = {
  desayuno:   "Desayuno",
  comida:     "Comida",
  comida_cena:"Comida / Cena",
  cena:       "Cena",
  snack:      "Snack",
};
const TIPO_COLORS = {
  desayuno:   "bg-yellow-100 text-yellow-800",
  comida:     "bg-green-100 text-green-800",
  comida_cena:"bg-orange-100 text-orange-800",
  cena:       "bg-blue-100 text-blue-800",
  snack:      "bg-purple-100 text-purple-800",
};

export default function RecipesPage() {
  const [recipes, setRecipes]   = useState([]);
  const [filter, setFilter]     = useState("");
  const [tipoFilter, setTipo]   = useState("");
  const [status, setStatus]     = useState(null); // pdf ingest status
  const [uploading, setUploading] = useState(false);
  const [editing, setEditing]   = useState(null); // recipe being edited
  const [editData, setEditData] = useState({});
  const fileRef = useRef();
  const pollRef = useRef();

  useEffect(() => {
    loadRecipes();
    checkStatus();
    return () => clearInterval(pollRef.current);
  }, []);

  async function loadRecipes() {
    try {
      const data = await api.recipes.list();
      setRecipes(data);
    } catch (e) {
      console.error(e);
    }
  }

  async function checkStatus() {
    try {
      const s = await api.pdf.status();
      setStatus(s);
      if (s.state === "running") {
        pollRef.current = setInterval(async () => {
          const s2 = await api.pdf.status();
          setStatus(s2);
          if (s2.state !== "running") {
            clearInterval(pollRef.current);
            if (s2.state === "done") loadRecipes();
          }
        }, 2000);
      }
    } catch (_) {}
  }

  async function handleUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    try {
      await api.pdf.upload(file);
      setStatus({ state: "running", message: "Procesando PDF…", count: 0 });
      checkStatus();
    } catch (err) {
      alert("Error: " + err.message);
    } finally {
      setUploading(false);
      fileRef.current.value = "";
    }
  }

  async function saveEdit() {
    try {
      await api.recipes.patch(editing.id, editData);
      setEditing(null);
      loadRecipes();
    } catch (err) {
      alert(err.message);
    }
  }

  async function deleteRecipe(id) {
    if (!confirm("¿Eliminar esta receta?")) return;
    await api.recipes.del(id);
    loadRecipes();
  }

  const filtered = recipes.filter((r) => {
    const matchTipo = !tipoFilter || r.tipo === tipoFilter;
    const matchName = !filter || r.nombre.toLowerCase().includes(filter.toLowerCase());
    return matchTipo && matchName;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <h1 className="text-2xl font-bold flex-1">Mis Recetas</h1>
        <input
          ref={fileRef}
          type="file"
          accept=".pdf"
          className="hidden"
          onChange={handleUpload}
        />
        <button
          className="btn-primary"
          onClick={() => fileRef.current.click()}
          disabled={uploading || status?.state === "running"}
        >
          {status?.state === "running" ? "⏳ Importando…" : "📄 Subir PDF"}
        </button>
      </div>

      {/* Ingest status banner */}
      {status && status.state !== "idle" && (
        <div
          className={`rounded-lg px-4 py-3 text-sm font-medium ${
            status.state === "running"
              ? "bg-yellow-50 text-yellow-800 border border-yellow-200"
              : status.state === "done"
              ? "bg-green-50 text-green-800 border border-green-200"
              : "bg-red-50 text-red-800 border border-red-200"
          }`}
        >
          {status.state === "running" && <span className="mr-2 animate-spin inline-block">⏳</span>}
          {status.message}
        </div>
      )}

      {/* Empty state */}
      {recipes.length === 0 && status?.state !== "running" && (
        <div className="card text-center py-16 text-gray-400">
          <p className="text-4xl mb-3">📄</p>
          <p className="font-medium">Sin recetas todavía</p>
          <p className="text-sm mt-1">Sube el PDF de tu nutricionista para empezar</p>
        </div>
      )}

      {/* Filters */}
      {recipes.length > 0 && (
        <div className="flex flex-wrap gap-2">
          <input
            className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm flex-1 min-w-40 focus:outline-none focus:ring-2 focus:ring-brand-500"
            placeholder="Buscar receta…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <select
            className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            value={tipoFilter}
            onChange={(e) => setTipo(e.target.value)}
          >
            <option value="">Todos</option>
            {TIPOS.map((t) => (
              <option key={t} value={t}>{TIPO_LABELS[t] || t}</option>
            ))}
          </select>
          <span className="text-sm text-gray-400 self-center">{filtered.length} recetas</span>
        </div>
      )}

      {/* Recipe grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((r) => (
          <div key={r.id} className="card flex flex-col gap-2">
            {/* Photo */}
            {r.foto && (
              <img
                src={`/photos/${r.foto}`}
                alt={r.nombre}
                className="w-full h-36 object-cover rounded-lg"
                onError={(e) => e.target.classList.add("hidden")}
              />
            )}

            {/* Body */}
            {editing?.id === r.id ? (
              <div className="space-y-2">
                <input
                  className="w-full border border-gray-200 rounded px-2 py-1 text-sm"
                  value={editData.nombre ?? r.nombre}
                  onChange={(e) => setEditData((d) => ({ ...d, nombre: e.target.value }))}
                />
                <select
                  className="w-full border border-gray-200 rounded px-2 py-1 text-sm"
                  value={editData.tipo ?? r.tipo}
                  onChange={(e) => setEditData((d) => ({ ...d, tipo: e.target.value }))}
                >
                  {TIPOS.map((t) => <option key={t} value={t}>{TIPO_LABELS[t] || t}</option>)}
                </select>
                <input
                  className="w-full border border-gray-200 rounded px-2 py-1 text-sm"
                  placeholder="Subtipo (avena, arroz…)"
                  value={editData.subtipo ?? r.subtipo ?? ""}
                  onChange={(e) => setEditData((d) => ({ ...d, subtipo: e.target.value }))}
                />
                <div className="flex gap-2">
                  <button className="btn-primary text-xs py-1" onClick={saveEdit}>Guardar</button>
                  <button className="btn-ghost text-xs py-1" onClick={() => setEditing(null)}>Cancelar</button>
                </div>
              </div>
            ) : (
              <>
                <p className="font-semibold text-sm leading-snug">{r.nombre}</p>
                <div className="flex gap-1.5 flex-wrap">
                  <span className={`badge ${TIPO_COLORS[r.tipo] || "bg-gray-100 text-gray-700"}`}>{TIPO_LABELS[r.tipo] || r.tipo}</span>
                  {r.subtipo && <span className="badge bg-gray-100 text-gray-600">{r.subtipo}</span>}
                  {r.page_number && (
                    <span className="badge bg-gray-50 text-gray-400">p.{r.page_number}</span>
                  )}
                </div>
                <p className="text-xs text-gray-400">{r.ingredientes.length} ingredientes</p>

                {/* Ingredients preview */}
                {r.ingredientes.length > 0 && (
                  <ul className="text-xs text-gray-500 space-y-0.5 max-h-24 overflow-y-auto">
                    {r.ingredientes.map((i) => (
                      <li key={i.id} className="flex justify-between">
                        <span>{i.nombre}</span>
                        <span className="text-gray-400 ml-2 shrink-0">
                          {i.cantidad} {i.unidad}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}

                <div className="flex gap-2 mt-auto pt-1">
                  <button
                    className="btn-ghost text-xs py-1"
                    onClick={() => { setEditing(r); setEditData({}); }}
                  >
                    ✏️ Editar
                  </button>
                  <button
                    className="btn-ghost text-xs py-1 text-red-500 hover:bg-red-50"
                    onClick={() => deleteRecipe(r.id)}
                  >
                    🗑️
                  </button>
                </div>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
