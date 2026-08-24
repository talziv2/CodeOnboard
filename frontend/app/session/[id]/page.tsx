"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import MapView from "@/components/MapView";
import AnalysisView from "@/components/AnalysisView";
import EvidenceDrawer from "@/components/EvidenceDrawer";
import RouteRail from "@/components/RouteRail";
import SectionOverview from "@/components/SectionOverview";
import LessonPanel from "@/components/LessonPanel";
import CodeViewer from "@/components/CodeViewer";
import SessionHeader from "@/components/SessionHeader";
import SessionTour from "@/components/tour/SessionTour";
import RebuildingOverlay from "@/components/RebuildingOverlay";
import SurfaceTabs from "@/components/lesson/SurfaceTabs";
import { getSession, jump, resetSession, sessionStart, setScope } from "@/lib/api";
import type { GraphNode, SessionGraph } from "@/lib/api";
import { buildRoute, spineLength } from "@/lib/graph-layout";
import { currentSection, splitJourney } from "@/lib/route-sections";
import { useSourcePane } from "@/lib/source-pane";
import { RAIL_REM, useBand, useRootFontPx, sourceMustOverlay } from "@/lib/layout-bands";
import Button from "@/components/ui/Button";
import { lessonUi } from "@/lib/flags";
import {
  activeTab, INITIAL_TABS, modeOf, reduceTabs, surfaceForTab, tabsFor,
  type SessionTab, type TabEvent, type TabState,
} from "@/lib/surfaceTabs";
import { unseenRouteChanges } from "@/lib/sessionLog";
import { arrivalNotice } from "@/lib/arrival";
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
  /**
   * Open or close the source pane.
   *
   * Opening chooses a mode WHEN THERE IS A CHOICE TO MAKE: if a docked third column
   * would leave the reading column under `LESSON_FLOOR`, the pane opens floating,
   * because a 300px-wide lesson is not a lesson. That is a default, not a lock —
   * the dock control is live either way, and the stored mode is what reopens next
   * time.
   */
  const setShowCode = (open: boolean) => {
    if (open && source.mode === "dock" && sourceMustOverlay(band, viewportWidth, source.dockWidth, rootFontPx)) {
      patchSource({ open: true, mode: "float" });
      return;
    }
    patchSource({ open });
  };
  const { width: viewportWidth, band } = useBand();
  const rootFontPx = useRootFontPx();
  // The rail has no track of its own in the narrow band; it opens over the page.
  const [railOpen, setRailOpen] = useState(false);
  // ── hiding the rail (UI note 4) ─────────────────────────────────────────────
  //
  // The route is orientation, and orientation is not always what the learner
  // wants the width for — a long trace path or a wide diff wants the column. So
  // the track can be given back, and the choice persists: someone who hid it did
  // not mean "until the next reload".
  //
  // Kept out of `prefs` deliberately. That module is display settings the learner
  // sets from a menu and expects everywhere; this is a per-device layout state
  // with its own control in the header, and folding it in would put a rail toggle
  // in the display panel where nobody would look for it.
  const [railHidden, setRailHidden] = useState(false);
  useEffect(() => {
    setRailHidden(window.localStorage.getItem("codeonboard:rail-hidden") === "1");
  }, []);
  const toggleRail = () => {
    setRailHidden((hidden) => {
      window.localStorage.setItem("codeonboard:rail-hidden", hidden ? "0" : "1");
      return !hidden;
    });
  };
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
  // The chapter overview is a LAYER over the lesson column, not a destination:
  // no route, no session state, and it never moves the current node. Closing it
  // puts the learner back exactly where they already were.
  const [overviewAreaId, setOverviewAreaId] = useState<string | null>(null);

  // The bar's tabs depend on whether a chapter overview is open — an overview has no
  // Understanding to show — so this array's identity legitimately changes.
  //
  // Which is why `dispatchTab` must NOT close over it. It used to, with a
  // no-dependency `useMemo` whose stability was load-bearing: a fresh `tabs` gave
  // `dispatchTab` a new identity, which re-fired the arrival effect below and pinned
  // the tab to Lesson forever. That made a correct change to `tabs` a latent bug, so
  // the reducer now reads the current tabs through a ref and keeps ONE identity for
  // the life of the page. The hazard is gone rather than documented.
  const tabs = useMemo(
    () => tabsFor(lessonUi(), { sectionOverview: overviewAreaId !== null }),
    [overviewAreaId]
  );
  const tabsRef = useRef(tabs);
  tabsRef.current = tabs;
  const [tabState, setTabState] = useState<TabState>(INITIAL_TABS);
  const dispatchTab = useCallback(
    (event: TabEvent) =>
      setTabState((current) => reduceTabs(current, event, tabsRef.current)),
    []
  );
  /**
   * The tab actually rendered, which is the remembered one only while the bar still
   * offers it — and the mode it belongs to, which is what the column branches on.
   *
   * `openedSection` already sends the learner to Lesson, so the clamp inside
   * `activeTab` should never fire — but "should never" plus a tab list that can
   * shrink underneath the state is how a bar ends up with no active tab and a column
   * rendering a surface nobody selected. Derived rather than corrected in an effect:
   * an effect would be a second thing that moves the tab, which is exactly what R5's
   * reducer exists to prevent.
   */
  const tab = activeTab(tabState, tabs);
  const mode = modeOf(tab);
  // Tabs with a change the learner has not looked at yet. S4 drives this from the
  // adaptation signals; the plumbing is here so the bar's dot is real as soon as
  // there is something to report. Visiting a tab clears its dot — see the effect
  // below — because the point of the dot is "you have not seen this", and looking
  // at it is what makes that false.
  const [unseen, setUnseen] = useState<SessionTab[]>([]);
  // Rewritten material the learner has not read. Durable, panel-owned — see
  // `onMaterialUnread` below and `lib/materialSeen.ts`.
  const [materialUnread, setMaterialUnread] = useState(false);
  // Which unit's evidence chain is open, if any. Null = closed.
  const [evidenceNodeId, setEvidenceNodeId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // ── starting over, and rebuilding: two actions, two waits ──────────────────
  //
  // `Start over` restores the same route from its persisted plan: no model call,
  // no new session id, milliseconds. `Rebuild learning path` is the old
  // behaviour — the whole pipeline, two to four minutes, a different route — and
  // it is the only one of the two that needs a progress surface.
  const [startingOver, setStartingOver] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [rebuildRunId, setRebuildRunId] = useState("");
  const [rebuildError, setRebuildError] = useState<string | null>(null);
  // Held so dismissing the rebuild's wait can drop the request rather than leave
  // a fetch resolving into a page that has moved on. The RUN is not cancelled —
  // see `sessionStart` — only our interest in its answer.
  const rebuildAbort = useRef<AbortController | null>(null);
  /**
   * Bumped by a reset, and used as a React `key` on the session body.
   *
   * A reset keeps the URL and the session id, so React would keep every child
   * mounted and its state alive — `LessonPanel`'s typed answer and its verdict
   * card, the open evidence drawer, the chapter overview. Remounting on a key is
   * deliberately preferred over clearing those one by one: the field-by-field
   * version is a list, and the next component with local state is the one nobody
   * remembers to add to it.
   */
  const [epoch, setEpoch] = useState(0);
  /**
   * A reset that failed, reported without taking the session down.
   *
   * Deliberately NOT the page-level `error`, which replaces the whole session
   * with a full-screen "couldn't load" and a retry button. That is right for a
   * graph that would not load and wrong for this: a failed reset changes nothing
   * on the server, so the learner is still mid-session with all their work — and
   * being thrown to an error page would suggest otherwise.
   */
  const [startOverError, setStartOverError] = useState<string | null>(null);
  // Owned here, not in LessonPanel, because two things end the journey now: the
  // walk running out, and `Finish session` in the header menu.
  const [finished, setFinished] = useState(false);
  const [scoping, setScoping] = useState(false);
  // Going back to the route. Its own flag rather than reusing a jump spinner: the
  // notice's button is the only thing that shows it, and it must not be disabled
  // by an unrelated navigation.
  const [returning, setReturning] = useState(false);
  // The arrival the learner has said "Stay here" to, by its timestamp. See the
  // note beside `arrivalDismissed` for why this is not a boolean.
  const [dismissedArrivalAt, setDismissedArrivalAt] = useState<string | null>(null);
  const [scopeNote, setScopeNote] = useState<string | null>(null);
  // A nonce rather than a boolean: `Replay the tour` has to be able to fire a
  // second time after the first replay has ended, and a flag that is already
  // true announces nothing.
  const [tourReplay, setTourReplay] = useState(0);
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

  /**
   * START OVER — the same route, from the first stop, with none of the work.
   *
   * One request, no model call, no new session id. The server returns the whole
   * restored graph in the shape `getSession` returns, so this swaps it in rather
   * than re-fetching, and the swap plus the epoch bump are the entire client-side
   * reset: `epoch` remounts the session body, which discards every child's local
   * state (see its declaration). What the key cannot reach is reset beside it —
   * page-level state, and the per-session "have I looked at the rail" mark, which
   * is about a history that no longer exists.
   *
   * `introduced` is cleared because chapter introductions are shown once per
   * visit to a chapter with nothing behind it, and after a reset there is nothing
   * behind any of them again. Leaving it would silently skip every introduction
   * for the rest of the session.
   */
  const startOver = useCallback(async () => {
    if (startingOver) return;
    setStartingOver(true);
    setStartOverError(null);
    try {
      const { graph: restored } = await resetSession(id);
      setGraph(restored);
      setFinished(false);
      introduced.current.clear();
      setDismissedArrivalAt(null);
      setOverviewAreaId(null);
      setEvidenceNodeId(null);
      setUnseen([]);
      setScopeNote(null);
      window.localStorage.removeItem(`codeonboard:rail-seen:${id}`);
      setRailSeenAt(null);
      setEpoch((n) => n + 1);
    } catch (e: unknown) {
      setStartOverError(
        e instanceof Error ? errorText(e.message) : t.session.startOverFailed
      );
    } finally {
      setStartingOver(false);
    }
  }, [id, startingOver]);

  /**
   * REBUILD — a new route for the same repository and the same answers.
   *
   * What `Start over` used to do, and the reason it needed splitting: this runs
   * the whole pipeline, so it is the landing page's two-to-four-minute wait
   * happening on top of a session the learner is already reading. It reports that
   * through `RebuildingOverlay`, on this run's own `progress_id`.
   */
  const rebuild = useCallback(async () => {
    if (!graph || rebuilding) return;
    const runId = crypto.randomUUID();
    const controller = new AbortController();
    rebuildAbort.current = controller;
    setRebuildRunId(runId);
    setRebuildError(null);
    setRebuilding(true);
    try {
      const { session_id } = await sessionStart(
        graph.repo_url, graph.goal, true, runId, controller.signal
      );
      // The overlay stays up across the push and is cleared by arrival — see the
      // effect below. Clearing it here would flash the old session in between.
      router.push(`/session/${session_id}`);
    } catch (e: unknown) {
      // Dismissed rather than failed: the learner already has the session they
      // asked to keep, and an error card about a wait they abandoned would report
      // their own decision back to them as a problem.
      if (controller.signal.aborted) return;
      setRebuildError(
        e instanceof Error ? errorText(e.message) : t.home.pipelineFailed
      );
    }
  }, [graph, rebuilding, router]);

  /**
   * Arriving at a different session ends the rebuild, whether it succeeded or not.
   *
   * `router.push` moves to a different `id` on the SAME route, so React keeps this
   * component mounted and a flag set before the push would survive it — leaving
   * the new session showing the old one's progress overlay. Keyed on `id` so the
   * state cannot outlive the session it described.
   */
  useEffect(() => {
    setRebuilding(false);
    setRebuildRunId("");
    setRebuildError(null);
    rebuildAbort.current = null;
  }, [id]);

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

  // ── A1's rail mark ──────────────────────────────────────────────────────────
  //
  // Route-shape changes the learner has not looked at the rail since. Only the four
  // kinds that MOVED something count: a mark on the rail is a claim that the rail
  // looks different, and a gap opening changes what is outstanding rather than what
  // the route is.
  //
  // Stored per session so it survives a reload — a change announced once and
  // forgotten on refresh is a change the learner never saw. `localStorage` rather
  // than the server: this is "have I looked", which is about this browser and this
  // person, not about the graph.
  const [railSeenAt, setRailSeenAt] = useState<string | null>(null);
  useEffect(() => {
    setRailSeenAt(window.localStorage.getItem(`codeonboard:rail-seen:${id}`));
  }, [id]);
  const routeChanges = graph ? unseenRouteChanges(graph, railSeenAt) : [];
  // Looking at the rail is what clears it. The rail is always on screen in the wide
  // band, so "viewed" means the map tab — the place the whole route is legible.
  useEffect(() => {
    if (tab !== "map") return;
    const now = new Date().toISOString();
    window.localStorage.setItem(`codeonboard:rail-seen:${id}`, now);
    setRailSeenAt(now);
  }, [tab, id]);

  // Looking at a tab is what makes "you have not seen this" false, so visiting
  // clears its dot. Never on a timer: a dot that expires unseen is a change the
  // learner was told about and then untold.
  useEffect(() => {
    setUnseen((current) => (current.includes(tab) ? current.filter((x) => x !== tab) : current));
  }, [tab]);

  // Esc returns from route mode to the lesson. Bound for the MODE rather than for
  // the map tab: Analysis is the same excursion from reading, and an Escape that
  // worked on one of the two and silently did nothing on the other would read as a
  // key that sometimes fails.
  useEffect(() => {
    if (mode !== "route") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") dispatchTab({ kind: "dismissedRoute" });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mode, dispatchTab]);

  const stops = useMemo(
    () => (graph ? buildRoute(graph.nodes, graph.edges) : []),
    [graph]
  );

  // How the learner reached the current stop, said on the stop itself.
  //
  // Derived HERE because it is a statement about the route, and this is where the
  // route lives — the same `stops` the rail is numbered from, so the notice cannot
  // quote a position the rail disagrees with.
  //
  // Dismissal is keyed on `arrival.at` rather than being a boolean: a later jump
  // is a new fact and must be said again, and a boolean would silence every
  // arrival for the rest of the session after the first "Stay here".
  const arrival = useMemo(
    () => arrivalNotice(graph?.arrival, graph?.current_node_id ?? null, stops),
    [graph?.arrival, graph?.current_node_id, stops]
  );
  const arrivalDismissed = dismissedArrivalAt === graph?.arrival?.at;

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

  // Rejoining the route. Same endpoint as a jump, with the intent that tells the
  // server this is the opposite act: it clears the arrival notice instead of
  // raising another one, while still being recorded — a log showing only
  // departures would imply the learner never came back.
  const handleReturnToRoute = async (nodeId: string) => {
    setReturning(true);
    setViewingFile(null);
    setViewingRange(null);
    setFocusKey((k) => k + 1);
    try {
      await jump(id, nodeId, "resume");
      await loadGraph();
    } catch (e: unknown) {
      setError(e instanceof Error ? errorText(e.message) : t.session.jumpFailed);
    } finally {
      setReturning(false);
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
        onReplayTour={() => setTourReplay((n) => n + 1)}
        onStartOver={startOver}
        startingOver={startingOver}
        // Absent on a payload from an older backend, which is the same situation
        // as a session with no plan — so it defaults to unavailable rather than
        // offering an action that would 409.
        canStartOver={graph.has_plan === true}
        onRebuild={rebuild}
        rebuilding={rebuilding}
        onFinish={() => setFinished(true)}
      />

      {/* A failed reset, said in place. The session behind it is untouched and
          still usable, which is why this is a strip rather than a screen. */}
      {startOverError && (
        <div
          role="alert"
          className="flex shrink-0 items-center justify-between gap-4 border-b border-rust/40 bg-rust/10 px-5 py-2"
        >
          <span className="text-meta text-paper">
            {t.session.startOverFailed} {startOverError}
          </span>
          <Button
            variant="chrome"
            size="xs"
            onClick={() => setStartOverError(null)}
          >
            {t.session.dismiss}
          </Button>
        </div>
      )}

      {/* `key={epoch}` is the reset (see the `epoch` declaration): a restore keeps
          the URL and the session id, so without it React would keep every child
          below mounted and holding the previous walk's state — a typed answer, a
          verdict card, an open drawer. */}
      <div
        key={epoch}
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
            band === "narrow" || railHidden ? null : `${RAIL_REM[band]}rem`,
            "minmax(0,1fr)",
            // `dock` means a column, whatever the viewport. Squeezing the lesson
            // is the learner's call to make; taking the choice away was not.
            mode === "learn" && showCode && openFile && source.mode === "dock"
              ? "var(--source-width)"
              : null,
          ]
            .filter(Boolean)
            .join(" "),
        }}
      >
        {band !== "narrow" && !railHidden && (
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
            onHide={toggleRail}
            onBriefing={() => router.push(`/session/${id}/welcome`)}
          />
        )}

        <div className="flex min-h-0 flex-col border-e border-rule">
          <SurfaceTabs
            tabs={tabs}
            active={tab}
            // Two independent signals on one bar: `changed` is the surface dot
            // from S4 (something landed where you were not looking), and the Map
            // tab additionally carries A1's route mark when the SHAPE of the
            // journey changed. Different claims, so they are not merged.
            changed={[
              ...unseen,
              // Durable, and additive to `unseen` rather than replacing it: the
              // two answer different questions and a dot is one bit either way.
              ...(materialUnread && !unseen.includes("lesson")
                ? ["lesson" as SessionTab]
                : []),
              ...(routeChanges.length > 0 && tab !== "map" ? ["map" as SessionTab] : []),
            ]}
            onPick={(picked) => dispatchTab({ kind: "picked", tab: picked })}
            onSwitchMode={(picked) => dispatchTab({ kind: "switchedMode", mode: picked })}
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
              {mode === "learn" && !showCode && openFile && (
                <Button variant="chrome" size="sm" onClick={() => setShowCode(true)}>
                  {t.session.showSource}
                </Button>
              )}
                {/* ONLY THE WAY BACK IN (UI note 4, second pass).
                    `Hide route` moved into the rail's own header, where a control
                    for a column belongs. `Show route` cannot live there — once the
                    rail is hidden there is no rail to hold it — so it stays here,
                    and only while it is the one that applies. Hidden in the narrow
                    band, where the rail has no track to give back: it is a sheet. */}
                {band !== "narrow" && railHidden && (
                  <Button variant="chrome" size="sm" onClick={toggleRail}>
                    {t.session.showRail}
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

          {/* THE MODE decides which column this is, not the tab. Learn mode's two
              tabs are two views of the SAME column — S3 splits its contents across
              them with `surfaceBlocks`, and both render the lesson arrangement —
              while route mode's two are whole views of the session. Branching on
              the mode is what stops a new tab in either mode from having to be
              added to a condition somewhere else. */}
          {mode === "learn" ? (
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
                  arrival={arrivalDismissed ? null : arrival}
                  onReturnToRoute={handleReturnToRoute}
                  onDismissArrival={() =>
                    setDismissedArrivalAt(graph.arrival?.at ?? null)
                  }
                  returningToRoute={returning}
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
                  // R1. The panel reports where something landed; this decides
                  // whether that is news. A change in the surface the learner is
                  // looking at is not news, and marking it would leave a stale dot
                  // waiting to appear the moment they switched away.
                  onSurfaceChanged={(changed) => {
                    if (changed === tab) return;
                    setUnseen((current) =>
                      current.includes(changed) ? current : [...current, changed]
                    );
                  }}
                  /* THE DURABLE HALF (M3). `unseen` is transient by design — a
                     verdict landing while you are on another tab is news that
                     stops being news once seen, and React state is right for it.
                     Rewritten material is different: it stays unread until the
                     learner actually looks, across reloads, so the panel owns
                     that fact (localStorage, keyed by node) and reports it here
                     rather than the page inferring it from a grading reply it
                     will forget. */
                  onMaterialUnread={setMaterialUnread}
                  // The consequence line's `Read it`. A learner click, so R5 is
                  // satisfied by the same reducer everything else goes through.
                  onGoToSurface={(target) => dispatchTab({ kind: "picked", tab: target })}
                />
              ) : (
                <p className="font-mono text-aside text-graphite">{t.session.firstLesson}</p>
              )}
            </div>
          ) : (
            /* Route mode. The map gets the whole column now — the session log was a
               288px sidebar pinned beside it, which cost the route a fifth of its
               width on every visit for a list that is usually three lines long, and
               it now sits in Analysis where the rest of the account of the journey
               is. */
            <div className="flex min-h-0 flex-1">
              <div data-tour="surface" className="min-h-0 flex-1">
                {tab === "map" ? (
                  <MapView
                    nodes={graph.nodes}
                    edges={graph.edges}
                    currentNodeId={currentNodeId}
                    repoUrl={graph.repo_url}
                    onGoToLesson={handleJump}
                  />
                ) : (
                  <AnalysisView graph={graph} onOpenEvidence={setEvidenceNodeId} />
                )}
              </div>
              {/* Progressive disclosure: the profile states a classification,
                  and this is where the learner sees what produced it. Outside the
                  tab branch, because both tabs of this mode can open it — the
                  patterns and bands in Analysis, and anything the map grows later —
                  and a drawer that closed itself on a tab switch would lose the
                  thing the learner opened it to read. */}
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

        {/* THE SOURCE PANE IS NEVER A MODAL.
            
            It used to become one whenever the viewport could not hold a third
            column: a `fixed inset-0` sheet with a `bg-ink/70` backdrop over
            everything, and `mode` forced to `dock` inside it. That took away all
            three things the pane can do — the backdrop froze the page behind it,
            forcing `dock` disabled the undock control, and the sheet's fixed
            `max-w-[34rem]` disabled resizing — for a pane whose entire job is to be
            READ ALONGSIDE the lesson. A reference you cannot look away from is not
            a reference.
            
            So there is one branch now. `dock` is a third column; `float` is a
            draggable, resizable window; both leave the rest of the page live. Where
            a dock genuinely will not fit, the pane OPENS floating — see
            `openSource` — which is a starting point rather than a lock: the dock
            control still works, and a learner who insists on docking in a narrow
            window gets what they asked for. */}
        {mode === "learn" && showCode && openFile && (
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

        {/* THE TOUR, over everything. Mounted inside the grid rather than beside
            it only because that is where the page's other overlays live; it is
            `fixed`, so the grid does not place it.

            It is handed the two pieces of session state it is allowed to watch and
            the two it is allowed to move — and it moves the tab through the SAME
            `dispatchTab` every other caller uses, so R5 holds for the tour as well
            (see `lib/surfaceTabs.ts`). */}
        <SessionTour
          ready={!!currentNodeId}
          fresh={graph.progress.stops_settled === 0}
          replay={tourReplay}
          ctx={{ tab, sourceOpen: showCode }}
          onTabEvent={dispatchTab}
          onSource={setShowCode}
        />

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
                // Closes the sheet first, like every other navigation out of it:
                // the briefing is a different page, so leaving the sheet up would
                // put it over a route the learner is no longer on.
                onBriefing={() => {
                  setRailOpen(false);
                  router.push(`/session/${id}/welcome`);
                }}
              />
            </div>
          </div>
        )}
      </div>

      {/* The REBUILD's wait, over everything including the tour: the session
          underneath is about to be replaced, so it must not be answerable while
          that happens. `Start over` has no equivalent and needs none — it returns
          in milliseconds. */}
      {rebuilding && (
        <RebuildingOverlay
          repoUrl={graph.repo_url}
          goal={graph.goal}
          progressId={rebuildRunId}
          error={rebuildError}
          onRetry={rebuild}
          onDismiss={() => {
            rebuildAbort.current?.abort();
            rebuildAbort.current = null;
            setRebuilding(false);
            setRebuildRunId("");
            setRebuildError(null);
          }}
        />
      )}
    </main>
  );
}
