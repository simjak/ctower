import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Gallery } from "./Gallery";
import { Bench, frameFrom } from "./t035/Screens";
import "../styles/app.css";

/**
 * The bench's own entry, separate from the app's.
 *
 * `gallery.html` is served by `vite dev` and is not an input to `vite build`,
 * so the component bench exists while a component is being built and reviewed
 * and ships in nothing.
 *
 * A whole-screen bench answers to `?bench=`, because some designs are a screen
 * rather than a component: T-CTW-035's board is thirteen columns in one shell
 * and a story-sized crop of it would prove nothing about the density that is
 * the whole question.
 */
const host = document.getElementById("root");
if (host === null) {
  throw new Error("the document has no #root to mount into");
}

const search = window.location.search;
const bench = new URLSearchParams(search).get("bench");

createRoot(host).render(
  <StrictMode>{bench === "t035" ? <Bench draw={frameFrom(search)} /> : <Gallery />}</StrictMode>
);
