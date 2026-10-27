import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import { Layout } from "./components/Layout";
import { GeneratePage } from "./pages/Generate";
import { HomePage } from "./pages/Home";
import { LoginPage } from "./pages/Login";
import { RunDetailPage } from "./pages/RunDetail";
import { RunsPage } from "./pages/Runs";
import { ScenarioDetailPage } from "./pages/ScenarioDetail";
import { ScenariosPage } from "./pages/Scenarios";
import { t } from "./i18n";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { token, ready, lang } = useAuth();
  if (!ready) return <p className="muted" style={{ padding: "2rem" }}>{t("loading", lang)}</p>;
  if (!token) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<HomePage />} />
        <Route path="/scenarios" element={<ScenariosPage />} />
        <Route path="/scenarios/:slug" element={<ScenarioDetailPage />} />
        <Route path="/generate" element={<GeneratePage />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/runs/:id" element={<RunDetailPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
