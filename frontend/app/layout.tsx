import "./globals.css";

export const metadata = { title: "DevOps AI Agent", description: "Controlled Kubernetes operations" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="es"><body>{children}</body></html>;
}
