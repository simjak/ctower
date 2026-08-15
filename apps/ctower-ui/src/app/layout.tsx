import "../../design-reference/app.css";
import "./conductor.css";
import type { Metadata, Viewport } from "next";
import type { ReactElement, ReactNode } from "react";

/**
 * The first stylesheet is imported straight from `design-reference/`, the
 * vendored approved mockup set. There is no second copy to fall out of step
 * with it: the rendered app and the design reference read the same bytes.
 *
 * The second adds the one shape that set has no rule for — the chat workspace
 * the operator's north star asks for — and is built only from the first's own
 * variables, so it inherits both themes and can introduce no token of its own.
 */

export const metadata: Metadata = {
  title: "ctower",
  description: "Read-only phase-1 operator surface over the ctower record.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  colorScheme: "light dark",
};

/* Light is the default; the stored choice is applied before first paint. */
const APPLY_STORED_THEME = `try{if(localStorage.getItem('ctower-theme')==='dark'){document.documentElement.classList.add('theme-dark')}}catch(e){}`;

export default function RootLayout({ children }: { readonly children: ReactNode }): ReactElement {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: APPLY_STORED_THEME }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
