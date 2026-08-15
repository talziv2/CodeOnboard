"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import MapView from "@/components/MapView";
import RouteRail from "@/components/RouteRail";
import LessonPanel from "@/components/LessonPanel";
import CodeViewer from "@/components/CodeViewer";
import { getSession, jump, sessionStart } from "@/lib/api";
import type { GraphNode, SessionGraph } from "@/lib/api";
import { buildRoute, spineLength } from "@/lib/graph-layout";
import { errorText, t } from "@/lib/strings";

export default function SessionPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [graph, setGraph] = useState<SessionGraph | null>(null);
  const [viewingFile, setViewingFile] = useState<string | null>(null);
  // Set only when the learner opened a SPECIFIC anchor of a multi-anchor unit.
  // Without it the pane highlighted the node's display range in whatever file
  // was opened, so step 2 of a flow opened the right file at the wrong lines.
  const [viewingRange, setViewingRange] = useState<[number, number] | null>(null);
  const [showCode, setShowCode] = useState(true);
  const [tab, setTab] = useState<"lesson" | "map">("lesson");
  const [error, setError] = useState<string | null>(null);
  const [restarting, setRestarting] = useState(false);

  const loadGraph = useCallback(async () => {
    try {
      setGraph(await getSession(id));
    } catch (e: unknown) {
      setError(e instanceof Error ? errorText(e.message) : t.session.loadFailed);
    }
  }, [id]);

  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

  // Esc returns from the map to the lesson.
  useEffect(() => {
    if (tab !== "map") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setTab("lesson");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tab]);

  const stops = useMemo(
    () => (graph ? buildRoute(graph.nodes, graph.edges) : []),
    [graph]
  );

  const handleAdvance = async () => {
    setViewingFile(null);
    setViewingRange(null);
    await loadGraph();
  };

  // Picking a stop on the map is a request to study it, so land on the lesson.
  const handleJump = async (node: GraphNode) => {
    setTab("lesson");
    setViewingFile(null);
    setViewingRange(null);
    try {
      await jump(id, node.id);
      await loadGraph();
    } catch (e: unknown) {
      setError(e instanceof Error ? errorText(e.message) : t.session.jumpFailed);
    }
  };

  if (error) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-ink px-6">
        <div className="flex max-w-sm flex-col gap-3 text-center">
          <p className="text-rust">{error}</p>
          <button
            onClick={() => { setError(null); loadGraph(); }}
            className="mx-auto rounded border border-rule px-4 py-2 text-sm text-graphite transition hover:border-signal-dim hover:text-signal"
          >
            {t.session.retryLoad}
          </button>
        </div>
      </main>
    );
  }

  if (!graph) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-ink">
        <p className="animate-pulse font-mono text-sm text-graphite">
          {t.session.loading}
        </p>
      </main>
    );
  }

  const currentNodeId = graph.current_node_id;
  const currentNode = graph.nodes.find((n) => n.id === currentNodeId);
  const currentStop = stops.find((s) => s.node.id === currentNodeId);
  const pct = Math.round(graph.readiness * 100);
  const openFile = viewingFile ?? currentNode?.file ?? null;
  // The node's stored range describes ITS display file and nothing else. Using
  // it for whatever file happens to be open highlights arbitrary lines in an
  // unrelated one, so it applies only when the two agree.
  const highlightForOpenFile =
    currentNode && openFile === currentNode.file
      ? { start: currentNode.line_start, end: currentNode.line_end }
      : null;
  const depth = graph.goal?.depth;

  return (
    <main className="flex h-screen flex-col overflow-hidden bg-ink">
      <header className="flex shrink-0 items-center gap-4 border-b border-rule bg-slab px-5 py-2.5">
        <span className="font-display text-[15px] tracking-tight text-chalk">
          {t.appName}
        </span>

        <span className="min-w-0 flex-1 truncate font-mono text-[11.5px] text-graphite">
          {graph.repo_url.replace(/^https?:\/\/github\.com\//, "")}
          {graph.goal?.primary_goal && (
            <> &nbsp;·&nbsp; <span className="text-signal">{graph.goal.primary_goal}</span></>
          )}
          {depth && <> &nbsp;·&nbsp; {t.session.depth[depth] ?? depth}</>}
        </span>

        <span className="flex shrink-0 items-center gap-2.5">
          <span className="font-mono text-[10px] uppercase tracking-[0.13em] text-graphite">
            {t.session.readiness}
          </span>
          <span className="h-1 w-24 overflow-hidden rounded-full bg-raise">
            <span
              className="block h-full rounded-full bg-gradient-to-r from-signal-dim to-signal transition-[width] duration-500"
              style={{ width: `${pct}%` }}
            />
          </span>
          <span className="font-mono text-xs tabular-nums text-chalk">{pct}%</span>
        </span>

        {tab === "lesson" && (
          <button
            onClick={() => setShowCode((v) => !v)}
            className="shrink-0 rounded border border-rule px-3 py-1.5 font-mono text-[10.5px] text-graphite transition hover:border-signal-dim hover:text-signal"
          >
            {showCode ? t.session.hideSource : t.session.showSource}
          </button>
        )}
        <button
          onClick={async () => {
            setRestarting(true);
            try {
              const { session_id } = await sessionStart(graph.repo_url, graph.goal, true);
              router.push(`/session/${session_id}`);
            } catch {
              setRestarting(false);
            }
          }}
          disabled={restarting}
          className="shrink-0 rounded border border-rule px-3 py-1.5 font-mono text-[10.5px] text-graphite transition hover:border-signal-dim hover:text-signal disabled:opacity-40"
        >
          {restarting ? t.session.startingOver : t.session.startOver}
        </button>
      </header>

      <div
        className="grid min-h-0 flex-1"
        style={{
          // The map wants the room, so the source column steps aside on that tab.
          gridTemplateColumns:
            tab === "lesson" && showCode && openFile
              ? "268px minmax(0,1fr) 340px"
              : "268px minmax(0,1fr)",
        }}
      >
        <RouteRail
          stops={stops}
          currentNodeId={currentNodeId}
          areas={graph.areas}
          onJump={handleJump}
          onExpand={() => setTab("map")}
        />

        <div className="flex min-h-0 flex-col border-e border-rule">
          <div className="flex shrink-0 items-center gap-1 border-b border-rule px-5">
            {([
              ["lesson", t.session.tabLesson],
              ["map", t.session.tabMap],
            ] as const).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setTab(key)}
                aria-current={tab === key ? "page" : undefined}
                className={`-mb-px border-b-2 px-3 py-2.5 font-mono text-[10.5px] uppercase tracking-[0.13em] transition ${
                  tab === key
                    ? "border-signal text-signal"
                    : "border-transparent text-graphite hover:text-chalk"
                }`}
              >
                {label}
              </button>
            ))}
            {tab === "map" && (
              <span className="ms-auto font-mono text-[10.5px] text-graphite">
                {t.session.mapHint(graph.nodes.length)}
              </span>
            )}
          </div>

          {tab === "lesson" ? (
            <div className="min-h-0 flex-1 overflow-y-auto px-7 py-6">
              {currentNodeId && currentNode ? (
                <LessonPanel
                  sessionId={id}
                  nodeId={currentNodeId}
                  node={currentNode}
                  position={currentStop?.position ?? 1}
                  total={spineLength(stops)}
                  isPrerequisite={currentStop?.isPrerequisite ?? false}
                  graph={graph}
                  onFileClick={(file, lineStart, lineEnd) => {
                    setViewingFile(file);
                    setViewingRange(
                      lineStart && lineEnd ? [lineStart, lineEnd] : null
                    );
                    setShowCode(true);
                  }}
                  onAdvance={handleAdvance}
                  onRespond={loadGraph}
                  onFinish={() => router.push("/")}
                />
              ) : (
                <p className="font-mono text-sm text-graphite">{t.session.firstLesson}</p>
              )}
            </div>
          ) : (
            <div className="min-h-0 flex-1">
              <MapView
                nodes={graph.nodes}
                edges={graph.edges}
                currentNodeId={currentNodeId}
                readiness={graph.readiness}
                repoUrl={graph.repo_url}
                onNodeClick={handleJump}
              />
            </div>
          )}
        </div>

        {tab === "lesson" && showCode && openFile && (
          <CodeViewer
            sessionId={id}
            filePath={openFile}
            // A chosen anchor wins; otherwise the node's display range, as
            // before. CodeViewer itself is unchanged — this is which range it
            // is handed, not how it renders one.
            highlightStart={viewingRange?.[0] ?? highlightForOpenFile?.start}
            highlightEnd={viewingRange?.[1] ?? highlightForOpenFile?.end}
            onClose={() => setShowCode(false)}
          />
        )}
      </div>
    </main>
  );
}
