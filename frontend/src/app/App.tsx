import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { BrowserRouter, NavLink, Route, Routes } from "react-router";

import { AssistantPage } from "../pages/AssistantPage";
import { DashboardPage } from "../pages/DashboardPage";
import { PortfolioPage } from "../pages/PortfolioPage";
import { SettingsPage } from "../pages/SettingsPage";
import { StockDetailPage } from "../pages/StockDetailPage";
import { WatchlistPage } from "../pages/WatchlistPage";

export const makeQueryClient = () =>
  new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false, retry: 1 } } });

const NAV = [
  ["/", "Dashboard"],
  ["/watchlist", "Watchlist"],
  ["/portfolio", "Paper Portfolio"],
  ["/assistant", "AI Assistant"],
  ["/settings", "Settings"],
] as const;

export function Shell() {
  return (
    <div className="shell">
      <a className="skip" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <div className="brand">
          Stock Assistant <span className="pill">Paper trading only</span>
        </div>
        <nav aria-label="Main">
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/"}>
              {label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main id="main">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/stocks/:symbol" element={<StockDetailPage />} />
          <Route path="/watchlist" element={<WatchlistPage />} />
          <Route path="/portfolio" element={<PortfolioPage />} />
          <Route path="/assistant" element={<AssistantPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<p>Page not found.</p>} />
        </Routes>
      </main>
      <footer className="footer">
        Educational decision-support tool. Not investment advice. No real orders are ever placed. Free market data may be
        delayed; check each freshness label.
      </footer>
    </div>
  );
}

export function App({ client = makeQueryClient() }: { client?: QueryClient }) {
  return (
    <QueryClientProvider client={client}>
      {/* Honour the OS "reduce motion" setting: transforms are dropped, opacity/colour fades remain. */}
      <MotionConfig reducedMotion="user">
        <BrowserRouter>
        <Shell />
        </BrowserRouter>
      </MotionConfig>
    </QueryClientProvider>
  );
}
