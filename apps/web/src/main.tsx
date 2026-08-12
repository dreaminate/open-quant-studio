import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ResearchWorkbench } from "@open-quant-studio/research-ui";
import "@open-quant-studio/research-ui/styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ResearchWorkbench />
  </StrictMode>,
);
