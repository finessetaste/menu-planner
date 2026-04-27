import { useState, useEffect } from "react";
import { api } from "../api";

function monday(offset = 0) {
  const d = new Date();
  d.setDate(d.getDate() - d.getDay() + 1 + offset * 7);
  return d.toISOString().split("T")[0];
}

export default function ShoppingListPage() {
  const [weekOffset, setWeekOffset] = useState(0);
  const [items, setItems]     = useState([]);
  const [newName, setNewName] = useState("");
  const [newQty, setNewQty]   = useState("");
  const [newUnit, setNewUnit] = useState("g");
  const [generating, setGenerating] = useState(false);

  const weekStart = monday(weekOffset);

  useEffect(() => { loadItems(); }, [weekStart]);

  async function loadItems() {
    const data = await api.shopping.list(weekStart);
    setItems(data);
  }

  async function generate() {
    setGenerating(true);
    try {
      await api.shopping.generate(weekStart);
      await loadItems();
    } finally {
      setGenerating(false);
    }
  }

  async function toggle(item) {
    await api.shopping.patch(item.id, { is_checked: !item.is_checked });
    setItems((prev) =>
      prev.map((i) => (i.id === item.id ? { ...i, is_checked: !i.is_checked } : i))
    );
  }

  async function addManual() {
    if (!newName.trim()) return;
    const item = await api.shopping.add(weekStart, {
      nombre: newName.trim(),
      cantidad: newQty ? parseFloat(newQty) : null,
      unidad: newUnit || null,
    });
    setItems((prev) => [...prev, item]);
    setNewName(""); setNewQty("");
  }

  async function del(id) {
    await api.shopping.del(id);
    setItems((prev) => prev.filter((i) => i.id !== id));
  }

  async function clearChecked() {
    await api.shopping.clearChecked(weekStart);
    setItems((prev) => prev.filter((i) => !i.is_checked));
  }

  const auto   = items.filter((i) => !i.is_manual);
  const manual = items.filter((i) => i.is_manual);
  const checkedCount = items.filter((i) => i.is_checked).length;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="flex items-center gap-2 flex-1">
          <button className="btn-ghost py-1" onClick={() => setWeekOffset((o) => o - 1)}>←</button>
          <h1 className="text-xl font-bold">
            Lista de Compra{" "}
            <span className="text-sm font-normal text-gray-400">
              (semana del {new Date(weekStart + "T12:00:00").toLocaleDateString("es-ES", { day: "numeric", month: "short" })})
            </span>
          </h1>
          <button className="btn-ghost py-1" onClick={() => setWeekOffset((o) => o + 1)}>→</button>
        </div>
        <div className="flex gap-2">
          <button className="btn-primary" onClick={generate} disabled={generating}>
            {generating ? "⏳ Generando…" : "⟳ Generar lista"}
          </button>
          {checkedCount > 0 && (
            <button className="btn-ghost text-red-500 hover:bg-red-50" onClick={clearChecked}>
              🗑️ Limpiar marcados ({checkedCount})
            </button>
          )}
        </div>
      </div>

      {/* Auto-generated items */}
      {auto.length > 0 && (
        <div className="card space-y-1">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
            Del plan semanal
          </p>
          {auto.map((item) => (
            <ShoppingRow key={item.id} item={item} onToggle={toggle} onDelete={del} />
          ))}
        </div>
      )}

      {/* Manual items */}
      {manual.length > 0 && (
        <div className="card space-y-1">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
            Añadidos manualmente
          </p>
          {manual.map((item) => (
            <ShoppingRow key={item.id} item={item} onToggle={toggle} onDelete={del} />
          ))}
        </div>
      )}

      {items.length === 0 && (
        <div className="card text-center py-12 text-gray-400">
          <p className="text-3xl mb-2">🛒</p>
          <p>Lista vacía. Selecciona recetas en el Plan Semanal y pulsa "Generar lista".</p>
        </div>
      )}

      {/* Add manual item */}
      <div className="card">
        <p className="text-sm font-semibold mb-3">Añadir ítem manual</p>
        <div className="flex flex-wrap gap-2">
          <input
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm flex-1 min-w-32 focus:outline-none focus:ring-2 focus:ring-brand-500"
            placeholder="Nombre del producto"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addManual()}
          />
          <input
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm w-20 focus:outline-none focus:ring-2 focus:ring-brand-500"
            placeholder="Cant."
            type="number"
            value={newQty}
            onChange={(e) => setNewQty(e.target.value)}
          />
          <select
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            value={newUnit}
            onChange={(e) => setNewUnit(e.target.value)}
          >
            {["g", "ml", "unidad", "l", "kg", "cucharada"].map((u) => (
              <option key={u} value={u}>{u}</option>
            ))}
          </select>
          <button className="btn-primary" onClick={addManual}>+ Añadir</button>
        </div>
      </div>
    </div>
  );
}

function ShoppingRow({ item, onToggle, onDelete }) {
  return (
    <div
      className={`flex items-center gap-3 py-2 px-1 rounded-lg transition-colors ${
        item.is_checked ? "opacity-50" : ""
      }`}
    >
      <button
        onClick={() => onToggle(item)}
        className={`w-5 h-5 rounded border-2 flex items-center justify-center shrink-0 transition-colors ${
          item.is_checked
            ? "bg-brand-600 border-brand-600 text-white"
            : "border-gray-300 hover:border-brand-500"
        }`}
      >
        {item.is_checked && <span className="text-xs">✓</span>}
      </button>
      <span className={`flex-1 text-sm ${item.is_checked ? "line-through text-gray-400" : ""}`}>
        {item.nombre}
        {item.cantidad && (
          <span className="text-gray-400 ml-1.5">
            {item.cantidad} {item.unidad}
          </span>
        )}
        {item.is_manual && (
          <span className="ml-2 text-xs text-purple-500">manual</span>
        )}
      </span>
      <button
        onClick={() => onDelete(item.id)}
        className="text-gray-300 hover:text-red-400 text-sm px-1"
      >
        ✕
      </button>
    </div>
  );
}
