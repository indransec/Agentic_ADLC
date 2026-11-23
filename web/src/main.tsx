import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app";
import "./ui/theme.css";

const root = document.getElementById("root");
if (root === null) {
  throw new Error("missing #root element");
}
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
