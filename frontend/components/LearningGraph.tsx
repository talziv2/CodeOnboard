"use client";

import ReactFlow, {
  Background,
  Controls,
  type Node,
  type Edge,
  type NodeTypes,
} from "reactflow";
import "reactflow/dist/style.css";
import type { GraphNode, GraphEdge, UnderstandingState } from "@/lib/api";

const stateColor: Record<UnderstandingState, string> = {
  not_started: "#374151",
  partial: "#92400e",
  understood: "#14532d",
};

const stateBorder: Record<UnderstandingState, string> = {
  not_started: "#6b7280",
  partial: "#d97706",
  understood: "#22c55e",
};

const nodeTypes: NodeTypes = {};

const NODE_W = 280;
const NODE_H = 90;
const COLS = 3;
const GAP_X = 60;
const GAP_Y = 50;

function toRFNodes(nodes: GraphNode[], currentNodeId: string | null): Node[] {
  return nodes.map((n, i) => {
    const isCurrent = n.id === currentNodeId;
    const col = i % COLS;
    const row = Math.floor(i / COLS);
    return {
      id: n.id,
      position: { x: col * (NODE_W + GAP_X), y: row * (NODE_H + GAP_Y) },
      data: {
        label: (
          <div style={{ textAlign: "left", padding: "4px 2px" }}>
            <div style={{
              fontWeight: 700,
              fontSize: 14,
              lineHeight: 1.4,
              color: "#f9fafb",
              marginBottom: 6,
            }}>
              {n.title}
            </div>
            <div style={{
              fontSize: 11,
              color: "#9ca3af",
              fontFamily: "monospace",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}>
              {n.file}
            </div>
          </div>
        ),
      },
      style: {
        background: stateColor[n.understanding_state] ?? stateColor.not_started,
        border: `2px solid ${isCurrent ? "#6366f1" : stateBorder[n.understanding_state] ?? "#6b7280"}`,
        borderRadius: 10,
        width: NODE_W,
        height: NODE_H,
        boxShadow: isCurrent ? "0 0 0 3px #6366f180, 0 4px 20px #6366f140" : "0 2px 8px rgba(0,0,0,0.4)",
        cursor: "pointer",
      },
    };
  });
}

function toRFEdges(edges: GraphEdge[]): Edge[] {
  return edges.map((e, i) => ({
    id: `e-${i}`,
    source: e.from_id,
    target: e.to_id,
    style: { stroke: "#4b5563", strokeWidth: 2 },
    animated: false,
  }));
}

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  currentNodeId: string | null;
  readiness: number;
  onNodeClick: (node: GraphNode) => void;
}

export default function LearningGraph({ nodes, edges, currentNodeId, readiness, onNodeClick }: Props) {
  const rfNodes = toRFNodes(nodes, currentNodeId);
  const rfEdges = toRFEdges(edges);
  const pct = Math.round(readiness * 100);

  const handleNodeClick = (_: React.MouseEvent, rfNode: Node) => {
    const original = nodes.find((n) => n.id === rfNode.id);
    if (original) onNodeClick(original);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", gap: 10 }}>
      {/* Readiness bar */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "0 4px" }}>
        <span style={{ fontSize: 13, color: "#9ca3af", whiteSpace: "nowrap" }}>Readiness</span>
        <div style={{ flex: 1, background: "#1f2937", borderRadius: 9999, height: 8 }}>
          <div style={{
            width: `${pct}%`,
            background: "linear-gradient(90deg, #4f46e5, #7c3aed)",
            height: 8,
            borderRadius: 9999,
            transition: "width 0.4s ease",
          }} />
        </div>
        <span style={{ fontSize: 14, color: "#fff", fontWeight: 700, minWidth: 36 }}>{pct}%</span>
      </div>

      {/* Graph */}
      <div style={{ flex: 1, borderRadius: 12, overflow: "hidden", border: "1px solid #1f2937", minHeight: 0 }}>
        <ReactFlow
          nodes={rfNodes}
          edges={rfEdges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.25 }}
          panOnDrag={false}
          zoomOnScroll={false}
          zoomOnPinch={false}
          zoomOnDoubleClick={false}
          preventScrolling={false}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          attributionPosition="bottom-right"
        >
          <Background color="#1f2937" gap={20} />
        </ReactFlow>
      </div>

      {/* Legend */}
      <div style={{ display: "flex", gap: 20, padding: "0 4px" }}>
        {(["not_started", "partial", "understood"] as UnderstandingState[]).map((s) => (
          <span key={s} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#9ca3af" }}>
            <span style={{
              display: "inline-block",
              width: 12,
              height: 12,
              borderRadius: 3,
              background: stateColor[s],
              border: `2px solid ${stateBorder[s]}`,
            }} />
            {s.replace("_", " ")}
          </span>
        ))}
      </div>
    </div>
  );
}
