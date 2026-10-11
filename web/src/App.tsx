import { useEffect, useState } from "react";
import { TopBar, type Page } from "./components/TopBar";
import { useDemo } from "./lib/useDemo";
import { DemoPage } from "./pages/DemoPage";
import { EvalsPage } from "./pages/EvalsPage";
import { RunsPage } from "./pages/RunsPage";

function readHash(): { page: Page; run: string | null } {
  const [p, run] = window.location.hash.replace(/^#\/?/, "").split("/");
  const page: Page = p === "runs" || p === "evals" ? p : "demo";
  return { page, run: run ?? null };
}

export default function App() {
  const [route, setRoute] = useState(readHash);
  const demo = useDemo();

  useEffect(() => {
    const on = () => setRoute(readHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  const go = (page: Page, run?: string) => {
    window.location.hash = page === "demo" ? "" : run ? `/${page}/${run}` : `/${page}`;
  };

  return (
    <div className="flex h-full min-w-[1200px] flex-col">
      <TopBar page={route.page} onPage={(p) => go(p)} info={demo.info} onReset={() => void demo.reset()} resetDisabled={demo.running} />
      <main className="min-h-0 flex-1">
        {demo.loadError ? (
          <div className="flex h-full items-center justify-center">
            <div className="rounded-2xl border border-rose-200 bg-white p-6 text-center shadow-sm">
              <div className="text-[15px] font-semibold text-rose-700">Cannot reach the server</div>
              <p className="mt-1 text-[13px] text-slate-500">{demo.loadError}. Start it with: uv run python -m safemoney</p>
            </div>
          </div>
        ) : route.page === "demo" ? (
          <DemoPage demo={demo} />
        ) : route.page === "runs" ? (
          <RunsPage key={route.run ?? "all"} focusId={route.run} />
        ) : (
          <EvalsPage info={demo.info} onOpenRun={(id) => go("runs", id)} />
        )}
      </main>
    </div>
  );
}
