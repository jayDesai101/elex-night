import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Analytics } from "@vercel/analytics/react";
import App from "./App";
import "./index.css";

const queryClient = new QueryClient();
// Vercel Web Analytics only exists on Vercel deployments; the self-hosted copy skips it.
const onVercel = window.location.hostname.endsWith(".vercel.app");

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
    {onVercel && <Analytics />}
  </React.StrictMode>
);
