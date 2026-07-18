import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { ClientRouter } from "./ClientRouter";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ClientRouter />
  </StrictMode>,
);
