"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import LearningGraph from "@/components/LearningGraph";
import LessonPanel from "@/components/LessonPanel";
import CodeViewer from "@/components/CodeViewer";
import { getSession } from "@/lib/api";
import type { SessionGraph, GraphNode } from "@/lib/api";

export default function SessionPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [graph, setGraph] = useState<SessionGraph | null>(null);
  const [activeNodeId, setActiveNodeId] = useState<string | null>(null);
  const [viewingFile, setViewingFile] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadGraph = useCallback(async () => {
    try {
      const data = await getSession(id);
      setGraph(data);
      if (data.current_node_id && !activeNodeId) {
        setActiveNodeId(data.current_node_id);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load session");
    }
  }, [id, activeNodeId]);

  useEffect(() => {
    loadGraph();
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleNodeClick = (node: GraphNode) => {
    setActiveNodeId(node.id);
    setViewingFile(null);
  };

  const handleAdvance = async () => {
    try {
      const data = await getSession(id);
      setGraph(data);
      if (data.current_node_id) setActiveNodeId(data.current_node_id);
      setViewingFile(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load session");
    }
  };

  if (error) {
    return (
      <main className="min-h-screen bg-gray-950 flex items-center justify-center">
        <p className="text-red-400">{error}</p>
      </main>
    );
  }

  if (!graph) {
    return (
      <main className="min-h-screen bg-gray-950 flex items-center justify-center">
        <p className="text-gray-400 animate-pulse">Loading session…</p>
      </main>
    );
  }

  const activeNode = graph.nodes.find((n) => n.id === activeNodeId);

  return (
    <main className="h-screen bg-gray-950 flex flex-col overflow-hidden">
      <header className="px-6 py-3 border-b border-gray-800 flex items-center gap-3 shrink-0">
        <h1 className="text-white font-bold text-lg">CodeOnboard</h1>
        <span className="text-gray-500 text-sm flex-1">Session {id.slice(0, 8)}…</span>
        <button
          onClick={() => router.push("/")}
          className="px-4 py-1.5 rounded-lg border border-gray-700 text-gray-400 hover:text-white hover:border-gray-500 text-sm transition"
        >
          Start over
        </button>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Left panel — graph OR code viewer */}
        <div className="flex-[3] flex flex-col p-4 overflow-hidden">
          {viewingFile && activeNode ? (
            <CodeViewer
              sessionId={id}
              filePath={viewingFile}
              highlightStart={activeNode.line_start}
              highlightEnd={activeNode.line_end}
              onClose={() => setViewingFile(null)}
            />
          ) : (
            <LearningGraph
              nodes={graph.nodes}
              edges={graph.edges}
              currentNodeId={graph.current_node_id}
              readiness={graph.readiness}
              onNodeClick={handleNodeClick}
            />
          )}
        </div>

        {/* Right panel — lesson */}
        <div className="flex-[2] border-l border-gray-800 p-6 overflow-y-auto">
          {activeNodeId ? (
            <LessonPanel
              sessionId={id}
              nodeId={activeNodeId}
              nodeTitle={activeNode?.title ?? ""}
              nodeFile={activeNode?.file}
              lineStart={activeNode?.line_start}
              lineEnd={activeNode?.line_end}
              onFileClick={(file) => setViewingFile(file)}
              onAdvance={handleAdvance}
            />
          ) : (
            <p className="text-gray-500 text-sm">Click a node to start learning.</p>
          )}
        </div>
      </div>
    </main>
  );
}
