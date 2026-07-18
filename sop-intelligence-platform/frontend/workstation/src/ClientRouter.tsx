import { useCallback, useEffect, useState } from "react";

import App from "./App";
import { AppNavigateContext, type AppRoute } from "./navContext";
import DemoPage from "./pages/DemoPage";

function readRoute(): AppRoute {
  const p = window.location.pathname.replace(/\/+$/, "") || "/";
  if (p === "/demo" || p.endsWith("/demo")) return "/demo";
  return "/";
}

/**
 * 无 react-router-dom：与 Vite SPA 配合，支持 / 与 /demo。
 */
export function ClientRouter() {
  const [route, setRoute] = useState<AppRoute>(readRoute);

  const navigate = useCallback((to: AppRoute) => {
    if (window.location.pathname !== to) {
      window.history.pushState({}, "", to);
    }
    setRoute(readRoute());
  }, []);

  useEffect(() => {
    const onPop = () => setRoute(readRoute());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  return (
    <AppNavigateContext.Provider value={navigate}>
      {route === "/demo" ? <DemoPage /> : <App />}
    </AppNavigateContext.Provider>
  );
}
