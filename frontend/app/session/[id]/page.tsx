"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import LearningGraph from "@/components/LearningGraph";
import LessonPanel from "@/components/LessonPanel";
import CodeViewer from "@/components/CodeViewer";
import { getSession } from "@/lib/api";
import type { SessionGraph } from "@/lib/api";

export default function SessionPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [graph, setGraph] = useState<SessionGraph | null>(null);
  const [viewingFile, setViewingFile] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadGraph = async () => {
    try {
      const data = await getSession(id);
      setGraph(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load session");
    }
  };

  useEffect(() => {
    loadGraph();
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleAdvance = async (): Promise<void> => {
    try {
      const data = await getSession(id);
      setGraph(data);
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

  const currentNodeId = graph.current_node_id;
  const currentNode = graph.nodes.find((n) => n.id === currentNodeId);

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
          {viewingFile && currentNode ? (
            <CodeViewer
              sessionId={id}
              filePath={viewingFile}
              highlightStart={currentNode.line_start}
              highlightEnd={currentNode.line_end}
              onClose={() => setViewingFile(null)}
            />
          ) : (
            <LearningGraph
              nodes={graph.nodes}
              edges={graph.edges}
              currentNodeId={currentNodeId}
              readiness={graph.readiness}
              onNodeClick={() => {}}
            />
          )}
        </div>

        {/* Right panel — lesson for current node */}
        <div className="flex-[2] border-l border-gray-800 p-6 overflow-y-auto">
          {currentNodeId ? (
            <LessonPanel
              sessionId={id}
              nodeId={currentNodeId}
              nodeTitle={currentNode?.title ?? ""}
              nodeFile={currentNode?.file}
              lineStart={currentNode?.line_start}
              lineEnd={currentNode?.line_end}
              onFileClick={(file) => setViewingFile(file)}
              onAdvance={handleAdvance}
              onFinish={() => router.push("/")}
            />
          ) : (
            <p className="text-gray-500 text-sm">Loading your first lesson…</p>
          )}
        </div>
      </div>
    </main>
  );
}
