import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LOA — Pesquisa com evidências",
  description: "Consulta rastreável às Leis Orçamentárias Anuais da União.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}

