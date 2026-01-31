import { BrowserRouter } from "react-router-dom";
import AppRoutes from "./app/routes/AppRoutes";

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
