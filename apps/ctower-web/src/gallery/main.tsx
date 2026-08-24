import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Gallery } from "./Gallery";
import "../styles/app.css";

/**
 * The bench's own entry, separate from the app's.
 *
 * `gallery.html` is served by `vite dev` and is not an input to `vite build`,
 * so the component bench exists while a component is being built and reviewed
 * and ships in nothing.
 */
const host = document.getElementById("root");
if (host === null) {
  throw new Error("the document has no #root to mount into");
}

createRoot(host).render(
  <StrictMode>
    <Gallery />
  </StrictMode>
);
