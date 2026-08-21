import "../../design-reference/app.css";
import "./setup/setup.css";
import type { Metadata, Viewport } from "next";
import type { ReactElement, ReactNode } from "react";

export const metadata: Metadata = {
  title: "ctower setup",
  description: "The retained shell for future company setup.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  colorScheme: "light dark",
};

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
