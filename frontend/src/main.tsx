import "./index.css";

import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { Toaster } from "sonner";

import App from "./App";
import { queryClient } from "./lib/queryClient";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
      <Toaster
        theme="dark"
        position="top-center"
        toastOptions={{ classNames: { toast: "!bg-elevated !border-border !text-foreground !rounded-2xl" } }}
      />
    </QueryClientProvider>
  </StrictMode>,
);
