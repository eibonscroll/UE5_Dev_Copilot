// web/pages/_app.tsx
import type { AppProps } from "next/app";
import Script from "next/script";

export default function App({ Component, pageProps }: AppProps) {
  return (
    <>
      {/* Load Mermaid in the browser (v11). */}
      <Script
        src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"
        strategy="afterInteractive"
      />
      <Component {...pageProps} />
    </>
  );
}
