import { Route, Routes } from "react-router-dom";
import { AppLayout } from "./layouts/AppLayout";
import { EvaluationPage } from "./pages/EvaluationPage";
import { ExplorerPage } from "./pages/ExplorerPage";
import { HistoryPage } from "./pages/HistoryPage";
import { NewQueryPage } from "./pages/NewQueryPage";
import { SchemaPage } from "./pages/SchemaPage";
import { SettingsPage } from "./pages/SettingsPage";

export function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<NewQueryPage />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="explorer" element={<ExplorerPage />} />
        <Route path="schema" element={<SchemaPage />} />
        <Route path="evaluation" element={<EvaluationPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route
          path="*"
          element={
            <div className="py-16 text-center">
              <p className="text-lg font-semibold">Page not found</p>
              <p className="mt-1 text-sm text-slate-500">Use the sidebar to get back to a page.</p>
            </div>
          }
        />
      </Route>
    </Routes>
  );
}
