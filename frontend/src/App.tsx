import { BrowserRouter } from "react-router-dom";
import AppRoutes from "./app/routes/AppRoutes";
import { AppStateProvider } from "./app/state/appState";
import { AuthProvider } from "./app/auth/AuthContext";
import DevAuthGate from "./app/auth/DevAuthGate";

export default function App() {
  return (
    <AppStateProvider>
      <AuthProvider>
        <BrowserRouter>
          <DevAuthGate>
            <AppRoutes />
          </DevAuthGate>
        </BrowserRouter>
      </AuthProvider>
    </AppStateProvider>
  );
}
