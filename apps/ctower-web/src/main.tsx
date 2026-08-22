import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import "./styles/app.css";

const host = document.getElementById("root");
if (host === null) {
  throw new Error("the document has no #root to mount into");
}

createRoot(host).render(
  <StrictMode>
    <App />
  </StrictMode>
);
