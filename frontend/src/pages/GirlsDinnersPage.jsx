import { useState, useEffect, useRef } from "react";
import { api } from "../api";

const DAY_NAMES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];

function monday(offset = 0) {
  const d = new Date();
  d.setDate(d.getDate() - d.getDay() + 1 + offset * 7);
  return d.toISOString().split("T")[0];
}

function fmtDate(iso) {
  return new Date(iso + "T12:00:00").toLocaleDateString("es-ES", {
    day: "numeric", month: "short",
  });
}

export default function GirlsDinnersPage() {
  const [weekOffset, setWeekOffset]   = useState(0);
  const [suggestions, setSuggestions] = useState([]);
  const [girlNames, setGirlNames]     = useState({ girl1: "Niña 1", girl2: "Niña 2" });
  const [editNames, setEditNames]     = useState(false);
  const [namesDraft, setNamesDraft]   = useState({});
  const [status, setStatus]           = useState({});
  const [loading, setLoading]         = useState(true);

  const weekStart = monday(weekOffset);

  useEffect(() => {
    Promise.all([
      api.girlsDinners.suggestions(weekStart),
      api.girlsDinners.getConfig(),
      api.girlsDinners.status(),
    ]).then(([s, cfg, st]) => {
      setSuggestions(s);
      setGirlNames(cfg);
      setStatus(st);
    }).finally(() => setLoading(false));
  }, [weekStart]);

  async function saveNames() {
    await api.girlsDinners.setConfig(namesDraft);
    setGirlNames(namesDraft);
    setEditNames(false);
  }

  async function selectDinner(girl, day, description) {
    await api.girlsDinners.select(girl, day, description);
    setSuggestions(prev =>
      prev.map(d =>
        d.date === day
          ? { ...d, girls: { ...d.girls, [girl]: { ...d.girls[girl], selected: description } } }
          : d
      )
    );
  }

  if (loading) return <div className="text-center py-16 text-gray-400">Cargando…</div>;

  const noData = suggestions.every(d =>
    !d.girls.girl1.lunch && !d.girls.girl1.scheduled_dinner &&
    !d.girls.girl2.lunch && !d.girls.girl2.scheduled_dinner
  );

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <h1 className="text-2xl font-bold flex-1">Cenas de las Niñas</h1>
        <button
          className="btn-ghost text-sm"
          onClick={() => { setEditNames(true); setNamesDraft({ ...girlNames }); }}
        >
          ✏️ Nombres
        </button>
      </div>

      {/* Edit names */}
      {editNames && (
        <div className="card flex flex-wrap gap-3 items-end">
          {["girl1", "girl2"].map(g => (
            <div key={g} className="flex flex-col gap-1">
              <label className="text-xs text-gray-500">{g === "girl1" ? "Niña 1" : "Niña 2"}</label>
              <input
                className="border border-gray-200 rounded px-3 py-1.5 text-sm"
                value={namesDraft[g] || ""}
                onChange={e => setNamesDraft(n => ({ ...n, [g]: e.target.value }))}
              />
            </div>
          ))}
          <button className="btn-primary" onClick={saveNames}>Guardar</button>
          <button className="btn-ghost" onClick={() => setEditNames(false)}>Cancelar</button>
        </div>
      )}

      {/* PDF Upload */}
      <UploadSection girlNames={girlNames} status={status} onDone={() => {
        api.girlsDinners.suggestions(weekStart).then(setSuggestions);
        api.girlsDinners.status().then(setStatus);
      }} />

      {/* Week nav */}
      <div className="flex items-center gap-3">
        <button className="btn-ghost" onClick={() => setWeekOffset(o => o - 1)}>← Ant.</button>
        <span className="flex-1 text-center text-sm font-medium text-gray-600">
          Semana del {fmtDate(weekStart)}
          {weekOffset === 0 && <span className="ml-2 text-brand-600">Esta semana</span>}
        </span>
        <button className="btn-ghost" onClick={() => setWeekOffset(o => o + 1)}>Sig. →</button>
      </div>

      {/* Empty state */}
      {noData && (
        <div className="card text-center py-12 text-gray-400">
          <p className="text-3xl mb-2">👧👧</p>
          <p>Sin datos. Sube los PDFs del cole para cada niña.</p>
        </div>
      )}

      {/* Days */}
      {!noData && (
        <div className="space-y-4">
          {suggestions.map((day, idx) => {
            const hasAny =
              day.girls.girl1.lunch || day.girls.girl1.scheduled_dinner ||
              day.girls.girl2.lunch || day.girls.girl2.scheduled_dinner;
            if (!hasAny) return null;
            return (
              <div key={day.date} className="card space-y-3">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-sm">{DAY_NAMES[idx]}</span>
                  <span className="text-xs text-gray-400">{fmtDate(day.date)}</span>
                </div>
                <div className="grid sm:grid-cols-2 gap-4">
                  {["girl1", "girl2"].map(girl => (
                    <GirlDayCard
                      key={girl}
                      girl={girl}
                      name={girlNames[girl]}
                      data={day.girls[girl]}
                      date={day.date}
                      onSelect={desc => selectDinner(girl, day.date, desc)}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function GirlDayCard({ girl, name, data, date, onSelect }) {
  const [open, setOpen] = useState(false);

  if (!data.lunch && !data.scheduled_dinner) {
    return (
      <div className="rounded-lg border border-dashed border-gray-200 p-3 text-xs text-gray-400 text-center">
        Sin datos para {name}
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-gray-100 bg-gray-50 p-3 space-y-2">
      <p className="font-semibold text-sm text-brand-700">{name}</p>

      {/* School lunch */}
      {data.lunch && (
        <div>
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-0.5">Comida cole</p>
          <p className="text-sm">{data.lunch}</p>
        </div>
      )}

      {/* Selected dinner */}
      <div>
        <p className="text-xs text-gray-400 uppercase tracking-wide mb-0.5">Cena seleccionada</p>
        {data.selected ? (
          <div className="flex items-start gap-2">
            <p className="text-sm flex-1">{data.selected}</p>
            <button
              className="text-xs text-brand-600 shrink-0"
              onClick={() => setOpen(o => !o)}
            >
              {open ? "▲" : "▼"} opciones
            </button>
          </div>
        ) : (
          <button
            className="text-sm text-brand-600 underline"
            onClick={() => setOpen(true)}
          >
            Seleccionar cena…
          </button>
        )}
      </div>

      {/* Options dropdown */}
      {open && (
        <div className="space-y-1 pt-1 border-t border-gray-200">
          <p className="text-xs text-gray-400 mb-1">
            {data.ranked_options?.length
              ? "Opciones (↑ menos repetición)"
              : "Sin opciones disponibles"}
          </p>
          {data.ranked_options?.map((opt, i) => (
            <button
              key={i}
              onClick={() => { onSelect(opt.description); setOpen(false); }}
              className={`w-full text-left text-xs px-2 py-1.5 rounded border transition-colors ${
                opt.description === data.selected
                  ? "border-brand-500 bg-brand-50 text-brand-700"
                  : "border-gray-200 hover:border-brand-400 hover:bg-brand-50"
              }`}
            >
              <span className="flex items-start gap-1.5">
                <span className={`shrink-0 font-mono font-bold ${opt.score === 0 ? "text-green-500" : opt.score === 1 ? "text-yellow-500" : "text-red-400"}`}>
                  {opt.score === 0 ? "✓" : `!${opt.score}`}
                </span>
                <span>
                  {opt.description}
                  {opt.is_scheduled && (
                    <span className="ml-1 text-gray-400">(sugerido cole)</span>
                  )}
                  {opt.conflicts?.length > 0 && (
                    <span className="ml-1 text-red-400">
                      repite: {opt.conflicts.join(", ")}
                    </span>
                  )}
                </span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── PDF Upload Section ────────────────────────────────────────────────────────

function UploadSection({ girlNames, status, onDone }) {
  const [uploading, setUploading] = useState(null);
  const refs = {
    girl1_both:   useRef(),
    girl2_lunch:  useRef(),
    girl2_dinner: useRef(),
  };

  async function upload(girl, meal_type, file) {
    setUploading(`${girl}_${meal_type}`);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("girl", girl);
    fd.append("meal_type", meal_type);
    try {
      await fetch("/api/girls-dinners/upload", { method: "POST", body: fd });
      // Poll until done
      const poll = setInterval(async () => {
        const st = await api.girlsDinners.status();
        const key = meal_type === "both" ? "both" : meal_type;
        if (st[girl]?.[key]?.state !== "running") {
          clearInterval(poll);
          setUploading(null);
          onDone();
        }
      }, 1500);
    } catch (e) {
      alert(e.message);
      setUploading(null);
    }
  }

  const uploads = [
    { key: "girl1_both",   girl: "girl1", meal_type: "both",   label: `${girlNames.girl1} — PDF cole (comida + cena)` },
    { key: "girl2_lunch",  girl: "girl2", meal_type: "lunch",  label: `${girlNames.girl2} — PDF comidas` },
    { key: "girl2_dinner", girl: "girl2", meal_type: "dinner", label: `${girlNames.girl2} — PDF cenas` },
  ];

  return (
    <div className="card">
      <p className="text-sm font-semibold mb-3">Subir PDFs del colegio</p>
      <div className="flex flex-wrap gap-2">
        {uploads.map(u => {
          const stKey = u.meal_type === "both" ? "both" : u.meal_type;
          const st = status[u.girl]?.[stKey];
          const busy = uploading === u.key;
          return (
            <div key={u.key} className="flex flex-col gap-1">
              <input
                ref={refs[u.key]}
                type="file"
                accept=".pdf"
                className="hidden"
                onChange={e => e.target.files[0] && upload(u.girl, u.meal_type, e.target.files[0])}
              />
              <button
                className="btn-ghost text-xs"
                disabled={busy}
                onClick={() => refs[u.key].current.click()}
              >
                {busy ? "⏳ Subiendo…" : `📄 ${u.label}`}
              </button>
              {st && st.state === "done" && (
                <span className="text-xs text-green-600">{st.message}</span>
              )}
              {st && st.state === "error" && (
                <span className="text-xs text-red-500">{st.message}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
