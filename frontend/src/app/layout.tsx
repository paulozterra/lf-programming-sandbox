import type { ReactNode } from "react";

export const metadata = {
  title: "LF sandbox",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="es-PE">
      <body>{children}</body>
    </html>
  );
}
