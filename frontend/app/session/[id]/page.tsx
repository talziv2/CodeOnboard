"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import MapView from "@/components/MapView";
import EvidenceDrawer from "@/components/EvidenceDrawer";
import RouteRail from "@/components/RouteRail";
import SectionOverview from "@/components/SectionOverview";
import LessonPanel from "@/components/LessonPanel";
import CodeViewer from "@/components/CodeViewer";
import SessionHeader from "@/components/SessionHeader";
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
  // Owned here, not in LessonPanel, because two things end the journey now: the
  // walk running out, and `Finish session` in the header menu.
  const [finished, setFinished] = useState(false);
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
        <p className="animate-pulse font-mono text-aside text-graphite">
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
      <SessionHeader
        graph={graph}
        depth={depth}
        pct={pct}
        stopCount={spineLength(stops)}
        scoping={scoping}
        scopeNote={scopeNote}
        onScope={adjustScope}
        sourceHidden={tab === "lesson" ? !showCode : undefined}
        onShowSource={() => setShowCode(true)}
        onBriefing={() => router.push(`/session/${id}/welcome`)}
        restarting={restarting}
        onStartOver={async () => {
          setRestarting(true);
          try {
            const { session_id } = await sessionStart(graph.repo_url, graph.goal, true);
            router.push(`/session/${session_id}`);
          } catch {
            setRestarting(false);
          }
        }}
        onFinish={() => setFinished(true)}
      />

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
                className={`-mb-px border-b-2 px-3 py-2.5 font-mono text-micro uppercase tracking-[0.13em] transition ${
                  tab === key
                    ? "border-signal text-signal"
                    : "border-transparent text-graphite hover:text-chalk"
                }`}
              >
                {label}
              </button>
            ))}
            {tab === "map" && (
              <span className="ms-auto font-mono text-micro text-graphite">
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
                  finished={finished}
                  onFinish={() => setFinished(true)}
                  onLeave={() => router.push("/")}
                />
              ) : (
                <p className="font-mono text-aside text-graphite">{t.session.firstLesson}</p>
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
