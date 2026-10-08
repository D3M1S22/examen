import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "EXAMEN OS",
  description: "Ambient Intelligence Dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        {/* We use standard sans fonts from Tailwind by default, 
            adding Inter/JetBrains via CDN or assuming local installation */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet" />
      </head>
      <body className="bg-background text-on-background">
        <div id="toast-container" className="fixed bottom-12 right-4 flex flex-col gap-2 z-[200]"></div>
        {children}
      </body>
    </html>
  );
}
