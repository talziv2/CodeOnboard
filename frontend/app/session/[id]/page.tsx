"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import MapView from "@/components/MapView";
import EvidenceDrawer from "@/components/EvidenceDrawer";
import RouteRail from "@/components/RouteRail";
import SectionOverview from "@/components/SectionOverview";
import LessonPanel from "@/components/LessonPanel";
import CodeViewer from "@/components/CodeViewer";
import SettingsMenu from "@/components/SettingsMenu";
import { getSession, jump, sessionStart, setScope } from "@/lib/api";
import type { GraphNode, SessionGraph } from "@/lib/api";
import { buildRoute, spineLength } from "@/lib/graph-layout";
import { currentSection, splitJourney } from "@/lib/route-sections";
import { useSourcePane } from "@/lib/source-pane";
import Button from "@/components/ui/Button";
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
  // A counter, not a flag: asking for a location the pane is *already* showing
  // still has to move it there. Nothing else changes when the same anchor is
  // clicked twice, so without this the pane would just sit where it was.
  const [focusKey, setFocusKey] = useState(0);
  const { source, patch: patchSource } = useSourcePane();
  const [tab, setTab] = useState<"lesson" | "map">("lesson");
  // Which unit's evidence chain is open, if any. Null = closed.
  const [evidenceNodeId, setEvidenceNodeId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [restarting, setRestarting] = useState(false);
  const [scoping, setScoping] = useState(false);
  const [scopeNote, setScopeNote] = useState<string | null>(null);
  // The chapter overview is a LAYER over the lesson column, not a destination:
  // no route, no session state, and it never moves the current node. Closing it
  // puts the learner back exactly where they already were.
  const [overviewAreaId, setOverviewAreaId] = useState<string | null>(null);
  // Sections already introduced this visit. Kept in a ref because it must not
  // cause a render, and paired with an evidence guard below — a section with
  // stops behind it is not new, whatever this page happens to remember.
  const introduced = useRef<Set<string>>(new Set());

  // §5.3: scope is derived from evidence, then adjusted against a plan the
  // learner can see. This is the "adjusted" half — it moves existing units
  // between priority buckets and never plans anything new.
  const adjustScope = async (direction: "shorter" | "deeper") => {
    setScoping(true);
    setScopeNote(null);
    try {
      const res = await setScope(id, direction);
      setScopeNote(
        !res.applied
          ? direction === "shorter"
            ? t.scope.nothingShorter
            : t.scope.nothingDeeper
          : direction === "shorter"
          ? t.scope.shortened(res.changed)
          : t.scope.deepened(res.changed)
      );
      await loadGraph();
    } catch {
      setScopeNote(t.scope.failed);
    } finally {
      setScoping(false);
    }
  };

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

  // Journey → section → stop, derived from the same graph the rail walks.
  const journey = useMemo(
    () => splitJourney(stops, graph?.areas ?? [], graph?.current_node_id ?? null),
    [stops, graph?.areas, graph?.current_node_id]
  );

  // Arriving in a new chapter shows its introduction once, in place of the
  // lesson, with "continue" one click away — no Next → Section → Start → Lesson
  // chain. It is offered only for a section with nothing behind it, so resuming
  // mid-chapter, re-reading a finished one, or reloading the page never
  // re-introduces anything.
  useEffect(() => {
    const section = currentSection(journey.sections);
    const areaId = section?.area?.id;
    if (!areaId || introduced.current.has(areaId)) return;
    const isFirstSeen = introduced.current.size === 0;
    introduced.current.add(areaId);
    if (!isFirstSeen && section!.settled === 0) setOverviewAreaId(areaId);
  }, [journey.sections]);

  // Esc closes the overview, like it returns from the map.
  useEffect(() => {
    if (!overviewAreaId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOverviewAreaId(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [overviewAreaId]);

  // Moving to another stop is also a request for a location — often in the file
  // already open, where nothing else would tell the pane to scroll.
  const handleAdvance = async () => {
    setViewingFile(null);
    setViewingRange(null);
    setFocusKey((k) => k + 1);
    await loadGraph();
  };

  // Picking a stop is a request to study it, so land on the lesson itself —
  // including from the section overview, which is what makes its lesson list a
  // way in rather than a table of contents.
  const handleJump = async (node: GraphNode) => {
    setTab("lesson");
    setOverviewAreaId(null);
    setViewingFile(null);
    setViewingRange(null);
    setFocusKey((k) => k + 1);
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
          <Button variant="secondary" size="md" className="mx-auto"
            onClick={() => { setError(null); loadGraph(); }}
           
          >
            {t.session.retryLoad}
          </Button>
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
  const pct = Math.round(graph.progress.goal_readiness * 100);
  const openFile = viewingFile ?? currentNode?.file ?? null;
  // The node's stored range describes ITS display file and nothing else. Using
  // it for whatever file happens to be open highlights arbitrary lines in an
  // unrelated one, so it applies only when the two agree.
  const highlightForOpenFile =
    currentNode && openFile === currentNode.file
      ? { start: currentNode.line_start, end: currentNode.line_end }
      : null;
  const depth = graph.goal?.depth;
  // Resolved from the live sections rather than trusted: a section whose stops
  // all became optional, or which a re-plan removed, simply stops being open.
  const overviewSection =
    journey.sections.find((s) => s.area?.id === overviewAreaId) ?? null;

  return (
    <main className="flex h-screen flex-col overflow-hidden bg-ink">
      <header className="flex shrink-0 items-center gap-4 border-b border-rule bg-slab px-5 py-2.5">
        <span className="font-display text-[calc(15rem/16)] tracking-tight text-chalk">
          {t.appName}
        </span>

        <span className="min-w-0 flex-1 truncate font-mono text-[calc(11.5rem/16)] text-graphite">
          {graph.repo_url.replace(/^https?:\/\/github\.com\//, "")}
          {graph.goal?.primary_goal && (
            <> &nbsp;·&nbsp; <span className="text-signal">{graph.goal.primary_goal}</span></>
          )}
          {depth && <> &nbsp;·&nbsp; {t.session.depth[depth] ?? depth}</>}
        </span>

        {/* TWO measures, side by side (learning-graph.md §5.4, decision OQ-1).
            Goal readiness is evidence — what has been demonstrated of what the
            goal requires. Journey is coverage — how far along the walk. Showing
            only the first reads 0% for a learner who walked every stop without
            answering; showing only the second claims understanding nobody
            demonstrated. */}
        <span className="flex shrink-0 items-center gap-2.5">
          <span className="font-mono text-[calc(10rem/16)] uppercase tracking-[0.13em] text-graphite">
            {t.session.demonstrated}
          </span>
          <span className="h-1 w-20 overflow-hidden rounded-full bg-raise">
            <span
              className="block h-full rounded-full bg-gradient-to-r from-signal-dim to-signal transition-[width] duration-500"
              style={{ width: `${pct}%` }}
            />
          </span>
          {/* The FRACTION is the number; the percentage is a gloss on it. "47%
              readiness" sounds like a calibrated prediction, where "7 / 15
              required objectives demonstrated" is a claim the learner can check
              against the journey below (M3a.3). */}
          <span
            className="font-mono text-xs tabular-nums text-chalk"
            title={t.map.coreDemonstrated(
              graph.progress.core_demonstrated,
              graph.progress.core_total
            )}
          >
            {graph.progress.core_demonstrated}/{graph.progress.core_total}
            <span className="text-graphite"> ({pct}%)</span>
          </span>
        </span>

        <span className="flex shrink-0 items-center gap-2.5">
          <span className="font-mono text-[calc(10rem/16)] uppercase tracking-[0.13em] text-graphite">
            {t.session.journey}
          </span>
          <span
            className="font-mono text-xs tabular-nums text-chalk"
            title={t.map.stopsTaken(
              graph.progress.stops_settled,
              graph.progress.stops_total
            )}
          >
            {t.session.journeyCount(
              graph.progress.stops_settled,
              graph.progress.stops_total
            )}
          </span>
        </span>

        {/* Scope control (U4). Sits in the header beside readiness because it
            is a statement about the whole journey, not about a stop. */}
        <span className="flex shrink-0 items-center gap-1.5">
          <span className="font-mono text-[calc(10rem/16)] uppercase tracking-[0.13em] text-graphite">
            {t.scope.label(spineLength(stops))}
          </span>
          <Button variant="chrome" size="xs"
            onClick={() => adjustScope("shorter")}
            disabled={scoping}
          >
            {scoping ? t.scope.working : t.scope.shorter}
          </Button>
          <Button variant="chrome" size="xs"
            onClick={() => adjustScope("deeper")}
            disabled={scoping}
          >
            {t.scope.deeper}
          </Button>
          {scopeNote && (
            <span className="font-mono text-[calc(10rem/16)] text-signal">{scopeNote}</span>
          )}
        </span>

        {tab === "lesson" && (
          <Button variant="chrome" size="sm" className="shrink-0"
            onClick={() => setShowCode((v) => !v)}
          >
            {showCode ? t.session.hideSource : t.session.showSource}
          </Button>
        )}
        {/* The briefing and the profile card stay reachable: what the system
            took the goal to be is worth re-reading mid-journey, and it is the
            page that explains why the lessons are pitched the way they are. */}
        <Button variant="chrome" size="sm" className="shrink-0"
          onClick={() => router.push(`/session/${id}/welcome`)}
        >
          {t.welcome.headerLink}
        </Button>
        <Button variant="chrome" size="sm" className="shrink-0"
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
        >
          {restarting ? t.session.startingOver : t.session.startOver}
        </Button>

        <SettingsMenu />
      </header>

      <div
        className="grid min-h-0 flex-1"
        style={{
          // The map wants the room, so the source column steps aside on that tab.
          // In rem, so the side columns grow with the text-size setting instead
          // of squeezing enlarged type into fixed-width chrome.
          // A floating pane is out of flow, so it claims no track — only the
          // docked one reserves a column, and its width is the variable the
          // divider drags (see `globals.css`).
          gridTemplateColumns:
            tab === "lesson" && showCode && openFile && source.mode === "dock"
              ? "16.75rem minmax(0,1fr) var(--source-width)"
              : "16.75rem minmax(0,1fr)",
        }}
      >
        <RouteRail
          sections={journey.sections}
          optional={journey.optional}
          currentNodeId={currentNodeId}
          openSectionId={overviewAreaId}
          onJump={handleJump}
          onOpenSection={(areaId) => {
            setTab("lesson");
            setOverviewAreaId(areaId);
          }}
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
                className={`-mb-px border-b-2 px-3 py-2.5 font-mono text-[calc(10.5rem/16)] uppercase tracking-[0.13em] transition ${
                  tab === key
                    ? "border-signal text-signal"
                    : "border-transparent text-graphite hover:text-chalk"
                }`}
              >
                {label}
              </button>
            ))}
            {tab === "map" && (
              <span className="ms-auto font-mono text-[calc(10.5rem/16)] text-graphite">
                {t.session.mapHint(graph.nodes.length)}
              </span>
            )}
          </div>

          {tab === "lesson" ? (
            <div className="min-h-0 flex-1 overflow-y-auto px-7 py-6">
              {overviewSection ? (
                <SectionOverview
                  section={overviewSection}
                  sections={journey.sections}
                  currentNodeId={currentNodeId}
                  onJump={handleJump}
                  onClose={() => setOverviewAreaId(null)}
                />
              ) : currentNodeId && currentNode ? (
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
                    setFocusKey((k) => k + 1);
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
            <div className="flex min-h-0 flex-1">
              <div className="min-h-0 flex-1">
                <MapView
                  nodes={graph.nodes}
                  edges={graph.edges}
                  currentNodeId={currentNodeId}
                  progress={graph.progress}
                  understanding={graph.understanding}
                  areas={graph.areas}
                  repoUrl={graph.repo_url}
                  onNodeClick={handleJump}
                  onOpenEvidence={setEvidenceNodeId}
                />
              </div>
              {/* Progressive disclosure: the profile states a classification,
                  and this is where the learner sees what produced it. */}
              {evidenceNodeId && (
                <EvidenceDrawer
                  sessionId={id}
                  nodeId={evidenceNodeId}
                  onClose={() => setEvidenceNodeId(null)}
                />
              )}
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
            focusKey={focusKey}
            source={source}
            onSourceChange={patchSource}
            onClose={() => setShowCode(false)}
          />
        )}
      </div>
    </main>
  );
}
