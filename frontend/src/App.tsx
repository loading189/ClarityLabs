import { BrowserRouter } from "react-router-dom";
import AppRoutes from "./app/routes/AppRoutes";
import { AppStateProvider } from "./app/state/appState";

export default function App() {
  return (
    <AppStateProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AppStateProvider>
  );
}
