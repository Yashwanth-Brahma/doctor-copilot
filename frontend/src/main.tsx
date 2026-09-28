import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";

// No StrictMode: in dev it runs effects twice, and the backend can't cancel a briefing once
// started, so every page load would run the local model twice.
createRoot(document.getElementById("root")!).render(<App />);
