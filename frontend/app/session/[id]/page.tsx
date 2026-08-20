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
import SurfaceTabs from "@/components/lesson/SurfaceTabs";
import { getSession, jump, sessionStart, setScope } from "@/lib/api";
import type { GraphNode, SessionGraph } from "@/lib/api";
import { buildRoute, spineLength } from "@/lib/graph-layout";
import { currentSection, splitJourney } from "@/lib/route-sections";
import { useSourcePane } from "@/lib/source-pane";
import { RAIL_REM, useBand, useRootFontPx, sourceMustOverlay } from "@/lib/layout-bands";
import Button from "@/components/ui/Button";
import { lessonUi } from "@/lib/flags";
import {
  nextTab, surfaceForTab, tabsFor, type SessionTab, type TabEvent,
} from "@/lib/surfaceTabs";
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
  // The pane's visibility is a persisted PREFERENCE, not page state: it now
  // defaults to closed and opens on a citation, so "was it open last time" is
  // the only thing worth carrying between sessions. `useSourcePane` reads it in
  // an effect, which is why the server-rendered markup matches — closed is both
  // the default and the first paint.
  // A counter, not a flag: asking for a location the pane is *already* showing
  // still has to move it there. Nothing else changes when the same anchor is
  // clicked twice, so without this the pane would just sit where it was.
  const [focusKey, setFocusKey] = useState(0);
  const { source, patch: patchSource } = useSourcePane();
  const showCode = source.open;
  const setShowCode = (open: boolean) => patchSource({ open });
  const { width: viewportWidth, band } = useBand();
  const rootFontPx = useRootFontPx();
  // The pane leaves the grid and becomes a sheet when the window cannot hold
  // three columns without starving the middle one. Decided from the viewport and
  // the pane's own width, never from the lesson's measured width — see
  // `sourceMustOverlay` for why that distinction matters.
  const sourceOverlay = sourceMustOverlay(band, viewportWidth, source.dockWidth, rootFontPx);
  // The rail has no track of its own in the narrow band; it opens over the page.
  const [railOpen, setRailOpen] = useState(false);
  // ── the tab, and the ONE way it moves (R5) ──────────────────────────────────
  //
  // `setTab` used to be callable from anywhere, and four places called it. None of
  // them was phase-driven, but nothing stopped a fifth from being: selecting the
  // tab a phase implies is a one-line change that would feel helpful and is exactly
  // the surprising navigation this design rules out.
  //
  // So the state moves only through `dispatchTab`, whose event type has no phase in
  // it. Breaking R5 now requires inventing an event and naming it, which is a thing
  // a reviewer can see.
  // `useMemo` with no deps, and its stability is LOAD-BEARING: `tabsFor` returns a
  // fresh array per call, so an unmemoized `tabs` would give `dispatchTab` a new
  // identity every render, re-firing the arrival effect below and pinning the tab to
  // Lesson forever. The flag is a build constant, so there is nothing to depend on.
  const tabs = useMemo(() => tabsFor(lessonUi()), []);
  const [tab, setTab] = useState<SessionTab>("lesson");
  const dispatchTab = useCallback(
    (event: TabEvent) => setTab((current) => nextTab(current, event, tabs)),
    [tabs]
  );
  // Tabs with a change the learner has not looked at yet. S4 drives this from the
  // adaptation signals; the plumbing is here so the bar's dot is real as soon as
  // there is something to report. Visiting a tab clears its dot — see the effect
  // below — because the point of the dot is "you have not seen this", and looking
  // at it is what makes that false.
  const [unseen, setUnseen] = useState<SessionTab[]>([]);
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

  // ARRIVAL RESETS THE TAB, and it is keyed on the current node rather than
  // dispatched from the handlers that cause it. There are four ways to arrive —
  // advancing, jumping from the rail or the map, being taken to a warm-up that was
  // just spliced in, and resuming a session — and a per-handler dispatch would have
  // to remember all four. This cannot forget one.
  //
  // Not a phase transition: `currentNodeId` changes because the learner navigated.
  // Landing on a new stop showing the previous stop's Understanding, its verdict and
  // gaps gone, would be showing them an empty room.
  // Reads the graph state directly: `currentNodeId` is derived below the loading
  // guards, and a hook cannot sit after an early return.
  const arrivedAt = graph?.current_node_id;
  useEffect(() => {
    if (!arrivedAt) return;
    dispatchTab({ kind: "arrivedAtStop" });
  }, [arrivedAt, dispatchTab]);

  // Looking at a tab is what makes "you have not seen this" false, so visiting
  // clears its dot. Never on a timer: a dot that expires unseen is a change the
  // learner was told about and then untold.
  useEffect(() => {
    setUnseen((current) => (current.includes(tab) ? current.filter((x) => x !== tab) : current));
  }, [tab]);

  // Esc returns from the map to the lesson.
  useEffect(() => {
    if (tab !== "map") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") dispatchTab({ kind: "dismissedMap" });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tab, dispatchTab]);

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
          // Three bands, three rail tracks, and a source column only when the
          // pane is genuinely docked in the layout — a floating pane and an
          // overlay sheet are both out of flow and claim no track.
          gridTemplateColumns: [
            band === "narrow" ? null : `${RAIL_REM[band]}rem`,
            "minmax(0,1fr)",
            tab !== "map" && showCode && openFile && source.mode === "dock" && !sourceOverlay
              ? "var(--source-width)"
              : null,
          ]
            .filter(Boolean)
            .join(" "),
        }}
      >
        {band !== "narrow" && (
          <RouteRail
            sections={journey.sections}
            optional={journey.optional}
            currentNodeId={currentNodeId}
            openSectionId={overviewAreaId}
            onJump={handleJump}
            onOpenSection={(areaId) => {
              dispatchTab({ kind: "openedSection" });
              setOverviewAreaId(areaId);
            }}
            onExpand={() => dispatchTab({ kind: "expandedMap" })}
            compact={band === "medium"}
          />
        )}

        <div className="flex min-h-0 flex-col border-e border-rule">
          <SurfaceTabs
            tabs={tabs}
            active={tab}
            changed={unseen}
            onPick={(picked) => dispatchTab({ kind: "picked", tab: picked })}
            /* The right side of the lesson bar, as one group rather than three
               things competing for `ms-auto`. */
            trailing={
              <>
              {tab === "map" && band !== "narrow" && (
                <span className="font-mono text-micro text-graphite">
                  {t.session.mapHint(graph.nodes.length)}
                </span>
              )}
              {/* Opening the source is not session management, so it does not
                  belong behind the overflow menu with Start over and Finish.
                  Lessons cite code throughout and the pane now starts closed, so
                  the way to open it has to be findable without already knowing
                  it exists.

                  It lives here rather than in the header for a measured reason:
                  the header is fully allocated — the goal zone is what is left
                  after the other three, and adding a ~109px control took it from
                  844px to ~735px at 1280 and raised S1's overflow floor from
                  657px to ~766px. This bar had 829px of empty space at the same
                  width. Right-aligned, because that is the edge the pane opens
                  against.

                  There is no matching Hide: the pane owns its own close, and this
                  disappears while it is open. */}
              {tab !== "map" && !showCode && openFile && (
                <Button variant="chrome" size="sm" onClick={() => setShowCode(true)}>
                  {t.session.showSource}
                </Button>
              )}
                {band === "narrow" && (
                  <button
                    onClick={() => setRailOpen(true)}
                    className="font-mono text-micro uppercase tracking-[0.13em] text-graphite transition hover:text-signal"
                  >
                    {t.rail.title}
                  </button>
                )}
              </>
            }
          />

          {/* `tab !== "map"` rather than `tab === "lesson"`, because `surfaces` adds
              a third tab that is also a lesson-column view. In S2 both Lesson and
              Understanding render THIS column unchanged; S3 is what splits its
              contents across the two using `surfaceBlocks`. Divergence one step at
              a time, from an arrangement already known to work. */}
          {tab !== "map" ? (
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
                  // Which surface the active tab means. Null under `next`, where
                  // there is one column and the panel draws all of it.
                  surface={surfaceForTab(tab)}
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

        {tab !== "map" && showCode && openFile && (
          sourceOverlay ? (
            /**
             * A sheet over the page rather than a third column. The pane keeps
             * its own dock/float controls and its own close — this changes where
             * it sits, not what it is — but it is forced to `dock` while it is a
             * sheet, because a floating window inside a full-width overlay is two
             * ways of being out of flow at once.
             */
            <div className="fixed inset-0 z-40 flex justify-end">
              <button
                aria-label={t.session.hideSource}
                onClick={() => setShowCode(false)}
                className="absolute inset-0 bg-ink/70"
              />
              <div className="relative flex h-full w-full max-w-[34rem] flex-col border-s border-rule bg-trench shadow-overlay">
                <CodeViewer
                  sessionId={id}
                  filePath={openFile}
                  highlightStart={viewingRange?.[0] ?? highlightForOpenFile?.start}
                  highlightEnd={viewingRange?.[1] ?? highlightForOpenFile?.end}
                  focusKey={focusKey}
                  source={{ ...source, mode: "dock" }}
                  onSourceChange={patchSource}
                  onClose={() => setShowCode(false)}
                />
              </div>
            </div>
          ) : (
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
          )
        )}

        {/* The route, in the band where it has no column of its own. Same
            component and the same handlers — jumping closes it, because the
            thing it navigates to is underneath it. */}
        {band === "narrow" && railOpen && (
          <div className="fixed inset-0 z-40 flex">
            <button
              aria-label={t.rail.close}
              onClick={() => setRailOpen(false)}
              className="absolute inset-0 bg-ink/70"
            />
            <div className="relative flex h-full w-[17rem] max-w-[85vw] flex-col bg-trench shadow-overlay">
              <RouteRail
                sections={journey.sections}
                optional={journey.optional}
                currentNodeId={currentNodeId}
                openSectionId={overviewAreaId}
                onJump={(node) => {
                  setRailOpen(false);
                  handleJump(node);
                }}
                onOpenSection={(areaId) => {
                  setRailOpen(false);
                  dispatchTab({ kind: "openedSection" });
                  setOverviewAreaId(areaId);
                }}
                onExpand={() => {
                  setRailOpen(false);
                  dispatchTab({ kind: "expandedMap" });
                }}
              />
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
