import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import axe from "axe-core";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { vi } from "vitest";

type Handler = (url: string, init?: RequestInit) => unknown;

/** Routes fetch calls by "METHOD path" prefix to canned JSON (or a status via {__status}). */
export function mockApi(routes: Record<string, unknown | Handler>) {
  const calls: { method: string; url: string; body?: unknown }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const key = Object.keys(routes)
      .filter((k) => {
        const [m, p] = k.split(" ");
        return m === method && url.startsWith(p);
      })
      .sort((a, b) => b.length - a.length)[0];
    if (!key) return new Response(JSON.stringify({ error: { code: "not_mocked", message: url } }), { status: 500 });
    const v = routes[key];
    const data = typeof v === "function" ? (v as Handler)(url, init) : v;
    if (data && typeof data === "object" && "__status" in data) {
      const { __status, ...rest } = data as { __status: number };
      return new Response(JSON.stringify(rest), { status: __status });
    }
    return data === undefined ? new Response(null, { status: 204 }) : new Response(JSON.stringify(data), { status: 200 });
  });
  return calls;
}

export function renderAt(ui: ReactNode, path = "/", pattern = "*") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={pattern} element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

export async function axeViolations(container: Element) {
  // color-contrast needs real layout/CSS, which jsdom lacks.
  const res = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  return res.violations.map((v) => `${v.id}: ${v.help} (${v.nodes.length})`);
}
