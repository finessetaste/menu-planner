import { useState, useEffect } from "react";
import { api } from "../api";

const DAY_NAMES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
const MEAL_LABELS = { desayuno: "☀️ Desayuno", comida: "🍽️ Comida", cena: "🌙 Cena", snack: "🍎 Snack" };
const DAY_TYPES = [
  { value: "intense_training", label: "Entreno intenso", color: "bg-red-100 text-red-700" },
  { value: "normal_training",  label: "Entreno normal",  color: "bg-blue-100 text-blue-700" },
  { value: "rest",             label: "Descanso",        color: "bg-gray-100 text-gray-600" },
];

function monday(offset = 0) {
  const d = new Date();
  d.setDate(d.getDate() - d.getDay() + 1 + offset * 7);
  return d.toISOString().split("T")[0];
}

export default function WeeklyPlanPage() {
  const [weekOffset, setWeekOffset] = useState(0);
  const [days, setDays] = useState([]);
  const [recipes, setRecipes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [copying, setCopying] = useState(false);

  const weekStart = monday(weekOffset);

  useEffect(() => {
    Promise.all([api.recipes.list(), api.weeklyPlan.get(weekStart)])
      .then(([r, d]) => { setRecipes(r); setDays(d); })
      .finally(() => setLoading(false));
  }, [weekStart]);

  async function patchDay(id, data) {
    const updated = await api.weeklyPlan.patchDay(id, data);
    setDays((prev) => prev.map((d) => (d.id === id ? updated : d)));
  }

  async function copyFromPrevious() {
    if (!confirm("¿Copiar las recetas de la semana anterior en esta semana?")) return;
    setCopying(true);
    try {
      const { copied } = await api.weeklyPlan.copyFromPrevious(weekStart);
      const fresh = await api.weeklyPlan.get(weekStart);
      setDays(fresh);
      alert(`${copied} recetas copiadas de la semana anterior.`);
    } catch (e) {
      alert(e.message);
    } finally {
      setCopying(false);
    }
  }

  async function patchSlot(slotId, recipeId) {
    try {
      await api.weeklyPlan.patchSlot(slotId, { recipe_id: recipeId || 0 });
      const fresh = await api.weeklyPlan.get(weekStart);
      setDays(fresh);
    } catch (e) {
      alert(e.message);
    }
  }

  // Slot → which recipe tipos are valid (mirrors backend SLOT_COMPATIBLE_TYPES)
  const SLOT_COMPATIBLE = {
    desayuno: ["desayuno", "comida"],
    comida:   ["comida", "comida_cena"],
    cena:     ["cena", "comida_cena"],
    snack:    ["snack"],
  };

  function recipesForType(tipo) {
    const valid = SLOT_COMPATIBLE[tipo] || [tipo];
    return recipes.filter((r) => valid.includes(r.tipo));
  }

  if (loading) return <div className="text-center py-16 text-gray-400">Cargando…</div>;

  return (
    <div className="space-y-4">
      {/* Week navigation */}
      <div className="flex items-center gap-3">
        <button className="btn-ghost" onClick={() => setWeekOffset((o) => o - 1)}>← Ant.</button>
        <h1 className="text-lg font-bold flex-1 text-center">
          Semana del {new Date(weekStart + "T12:00:00").toLocaleDateString("es-ES", { day: "numeric", month: "long" })}
          {weekOffset === 0 && <span className="ml-2 text-xs text-brand-600 font-medium">Esta semana</span>}
        </h1>
        <button className="btn-ghost" onClick={() => setWeekOffset((o) => o + 1)}>Sig. →</button>
      </div>
      <div className="flex justify-end">
        <button
          className="btn-ghost text-xs flex items-center gap-1 text-gray-500 hover:text-brand-600"
          onClick={copyFromPrevious}
          disabled={copying}
          title="Copia todas las recetas de la semana anterior a esta semana"
        >
          {copying ? "Copiando…" : "📋 Copiar semana anterior"}
        </button>
      </div>

      {recipes.length === 0 && (
        <div className="card text-center py-8 text-gray-400">
          <p>Sin recetas. Sube el PDF en la sección Recetas primero.</p>
        </div>
      )}

      {/* Day columns — horizontal scroll on mobile */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-7">
        {days.map((day) => {
          const dayType = DAY_TYPES.find((t) => t.value === day.day_type) || DAY_TYPES[1];
          const dateLabel = new Date(
            new Date(weekStart + "T12:00:00").getTime() + day.day_index * 86400000
          ).toLocaleDateString("es-ES", { day: "numeric", month: "short" });

          return (
            <div key={day.id} className="card space-y-3 min-w-0">
              {/* Day header */}
              <div>
                <p className="font-bold text-sm">{DAY_NAMES[day.day_index]}</p>
                <p className="text-xs text-gray-400">{dateLabel}</p>
              </div>

              {/* Day type */}
              <select
                className={`w-full text-xs rounded px-2 py-1 font-medium border-0 ${dayType.color}`}
                value={day.day_type}
                onChange={(e) => patchDay(day.id, { day_type: e.target.value })}
              >
                {DAY_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>

              {/* Office toggle */}
              <label className="flex items-center gap-2 text-xs text-gray-600 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={day.is_office_day}
                  onChange={(e) => patchDay(day.id, { is_office_day: e.target.checked })}
                  className="accent-brand-600"
                />
                Día de oficina
              </label>

              {/* Meal slots */}
              {["desayuno", "comida", "cena", "snack"].map((mt) => {
                const slot = day.meal_slots.find((s) => s.meal_type === mt);
                if (!slot) return null;
                const options = recipesForType(mt);
                return (
                  <div key={mt} className="space-y-1">
                    <p className="text-xs font-medium text-gray-500">{MEAL_LABELS[mt]}</p>
                    {slot.is_fixed ? (
                      <div className="flex items-center gap-1">
                        <span className="text-xs bg-amber-100 text-amber-700 px-2 py-1 rounded w-full truncate">
                          🔒 {slot.recipe?.nombre || "Fijo (sin asignar)"}
                        </span>
                      </div>
                    ) : (
                      <select
                        className="w-full text-xs border border-gray-200 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-brand-500"
                        value={slot.recipe_id || ""}
                        onChange={(e) => patchSlot(slot.id, e.target.value ? parseInt(e.target.value) : 0)}
                      >
                        <option value="">— sin selección —</option>
                        {options.map((r) => (
                          <option key={r.id} value={r.id}>{r.nombre}</option>
                        ))}
                      </select>
                    )}
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}
