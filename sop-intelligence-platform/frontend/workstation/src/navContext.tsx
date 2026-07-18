import { createContext, useContext } from "react";

export type AppRoute = "/" | "/demo";

export const AppNavigateContext = createContext<(to: AppRoute) => void>(() => {});

export function useAppNavigate() {
  return useContext(AppNavigateContext);
}
