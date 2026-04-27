import { Routes, Route, Navigate } from "react-router-dom";
import Navbar from "./components/Navbar";
import RecipesPage from "./pages/RecipesPage";
import WeeklyPlanPage from "./pages/WeeklyPlanPage";
import ShoppingListPage from "./pages/ShoppingListPage";
import SettingsPage from "./pages/SettingsPage";
import GirlsDinnersPage from "./pages/GirlsDinnersPage";

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />
      <main className="flex-1 max-w-5xl mx-auto w-full px-4 py-6">
        <Routes>
          <Route path="/"            element={<Navigate to="/recetas" replace />} />
          <Route path="/recetas"     element={<RecipesPage />} />
          <Route path="/plan"        element={<WeeklyPlanPage />} />
          <Route path="/cenas-ninas" element={<GirlsDinnersPage />} />
          <Route path="/compra"      element={<ShoppingListPage />} />
          <Route path="/ajustes"     element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  );
}
