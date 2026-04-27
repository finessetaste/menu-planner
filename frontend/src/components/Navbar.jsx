import { NavLink } from "react-router-dom";

const links = [
  { to: "/recetas",      icon: "📋", label: "Recetas" },
  { to: "/plan",         icon: "📅", label: "Mi Plan" },
  { to: "/cenas-ninas",  icon: "👧", label: "Niñas" },
  { to: "/compra",       icon: "🛒", label: "Compra" },
  { to: "/ajustes",      icon: "⚙️", label: "Ajustes" },
];

export default function Navbar() {
  return (
    <>
      {/* Desktop top bar */}
      <header className="hidden sm:flex items-center gap-6 bg-white border-b border-gray-200 px-6 py-3 shadow-sm">
        <span className="text-xl font-bold text-brand-600 mr-4">🥗 Menu Planner</span>
        {links.map((l) => (
          <NavLink
            key={l.to}
            to={l.to}
            className={({ isActive }) =>
              `flex items-center gap-1.5 text-sm font-medium px-3 py-1.5 rounded-lg transition-colors ${
                isActive
                  ? "bg-brand-50 text-brand-700"
                  : "text-gray-600 hover:text-brand-700 hover:bg-brand-50"
              }`
            }
          >
            <span>{l.icon}</span>
            {l.label}
          </NavLink>
        ))}
      </header>

      {/* Mobile bottom tab bar */}
      <nav className="sm:hidden fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 flex z-50">
        {links.map((l) => (
          <NavLink
            key={l.to}
            to={l.to}
            className={({ isActive }) =>
              `flex-1 flex flex-col items-center py-2 text-xs font-medium transition-colors ${
                isActive ? "text-brand-600" : "text-gray-500"
              }`
            }
          >
            <span className="text-xl">{l.icon}</span>
            {l.label}
          </NavLink>
        ))}
      </nav>

      {/* Mobile bottom padding */}
      <div className="sm:hidden h-16" />
    </>
  );
}
