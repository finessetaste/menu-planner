import { useState, useEffect } from "react";
import { api } from "../api";

const MEAL_TYPES = ["desayuno", "comida", "cena", "snack"];
const DAY_TYPES = ["intense_training", "normal_training", "rest"];
const DAY_LABELS = {
  intense_training: "Entreno intenso",
  normal_training: "Entreno normal",
  rest: "Descanso",
};

export default function SettingsPage() {
  const [config, setConfig]   = useState(null);
  const [recipes, setRecipes] = useState([]);
  const [saved, setSaved]     = useState(false);

  useEffect(() => {
    Promise.all([api.config.get(), api.recipes.list()]).then(([c, r]) => {
      setConfig(c);
      setRecipes(r);
    });
  }, []);

  async function save() {
    await api.config.set(config);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  function setTarget(dayType, val) {
    setConfig((c) => ({
      ...c,
      calorie_targets: { ...c.calorie_targets, [dayType]: parseInt(val) || 0 },
    }));
  }

  function setBreakdown(mealType, val) {
    const num = parseFloat(val) || 0;
    setConfig((c) => ({
      ...c,
      calorie_breakdown: { ...c.calorie_breakdown, [mealType]: num / 100 },
    }));
  }

  function setOfficeFixed(mealType, recipeId) {
    setConfig((c) => ({
      ...c,
      office_fixed: {
        ...c.office_fixed,
        [mealType]: recipeId ? parseInt(recipeId) : null,
      },
    }));
  }

  if (!config) return <div className="text-center py-16 text-gray-400">Cargando…</div>;

  const breakdownSum = Object.values(config.calorie_breakdown).reduce((a, b) => a + b, 0);
  const breakdownOk = Math.abs(breakdownSum - 1) < 0.01;

  return (
    <div className="space-y-6 max-w-xl">
      <h1 className="text-2xl font-bold">Ajustes</h1>

      {/* Calorie targets */}
      <div className="card space-y-4">
        <h2 className="font-semibold text-sm text-gray-700 uppercase tracking-wide">
          Calorías objetivo por tipo de día
        </h2>
        {DAY_TYPES.map((dt) => (
          <div key={dt} className="flex items-center gap-3">
            <label className="flex-1 text-sm">{DAY_LABELS[dt]}</label>
            <input
              type="number"
              className="w-24 border border-gray-200 rounded-lg px-3 py-1.5 text-sm text-right focus:outline-none focus:ring-2 focus:ring-brand-500"
              value={config.calorie_targets[dt] || ""}
              onChange={(e) => setTarget(dt, e.target.value)}
            />
            <span className="text-sm text-gray-400 w-8">kcal</span>
          </div>
        ))}
      </div>

      {/* Calorie breakdown */}
      <div className="card space-y-4">
        <h2 className="font-semibold text-sm text-gray-700 uppercase tracking-wide">
          Distribución calórica por comida (%)
        </h2>
        {MEAL_TYPES.map((mt) => (
          <div key={mt} className="flex items-center gap-3">
            <label className="flex-1 text-sm capitalize">{mt}</label>
            <input
              type="number"
              min="0"
              max="100"
              step="1"
              className="w-20 border border-gray-200 rounded-lg px-3 py-1.5 text-sm text-right focus:outline-none focus:ring-2 focus:ring-brand-500"
              value={Math.round((config.calorie_breakdown[mt] || 0) * 100)}
              onChange={(e) => setBreakdown(mt, e.target.value)}
            />
            <span className="text-sm text-gray-400 w-4">%</span>
          </div>
        ))}
        <p className={`text-xs ${breakdownOk ? "text-green-600" : "text-red-500"}`}>
          Total: {Math.round(breakdownSum * 100)}%{" "}
          {!breakdownOk && "— debe sumar 100%"}
        </p>
      </div>

      {/* Office day fixed meals */}
      <div className="card space-y-4">
        <h2 className="font-semibold text-sm text-gray-700 uppercase tracking-wide">
          Comidas fijas en días de oficina
        </h2>
        <p className="text-xs text-gray-500">
          En días de oficina, el desayuno y el snack son fijos y no aparecen en los desplegables.
        </p>
        {["desayuno", "snack"].map((mt) => {
          const options = recipes.filter((r) => r.tipo === mt);
          return (
            <div key={mt} className="flex items-center gap-3">
              <label className="flex-1 text-sm capitalize">{mt}</label>
              <select
                className="flex-1 border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                value={config.office_fixed[mt] || ""}
                onChange={(e) => setOfficeFixed(mt, e.target.value)}
              >
                <option value="">— ninguno —</option>
                {options.map((r) => (
                  <option key={r.id} value={r.id}>{r.nombre}</option>
                ))}
              </select>
            </div>
          );
        })}
      </div>

      {/* Save */}
      <div className="flex items-center gap-3">
        <button className="btn-primary" onClick={save}>
          {saved ? "✓ Guardado" : "Guardar cambios"}
        </button>
        {saved && <span className="text-sm text-green-600">Configuración actualizada</span>}
      </div>
    </div>
  );
}
