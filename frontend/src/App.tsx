import { BrowserRouter, Route, Routes } from "react-router-dom";

import { ProtectedLayout } from "./components/ProtectedLayout";
import { AuthProvider } from "./context/AuthContext";
import { AskAiPage } from "./pages/AskAiPage";
import { DashboardPage } from "./pages/DashboardPage";
import { IngestionPage } from "./pages/IngestionPage";
import { LoginPage } from "./pages/LoginPage";
import { ReviewPage } from "./pages/ReviewPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TransactionsPage } from "./pages/TransactionsPage";

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<ProtectedLayout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/transactions" element={<TransactionsPage />} />
            <Route path="/ask-ai" element={<AskAiPage />} />
            <Route path="/ingestion" element={<IngestionPage />} />
            <Route path="/review" element={<ReviewPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
