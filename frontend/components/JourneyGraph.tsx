"use client";

import ReactFlow, {
  Background,
  type Node,
  type Edge,
  type NodeTypes,
} from "reactflow";
import "reactflow/dist/style.css";
import type { GraphNode, GraphEdge, UnderstandingState } from "@/lib/api";

const stateColor: Record<UnderstandingState, string> = {
  not_started: "#374151",
  "failed": "#7f1d1d",
  partial: "#92400e",
  understood: "#14532d",
};

const stateBorder: Record<UnderstandingState, string> = {
  not_started: "#6b7280",
  "failed": "#ef4444",
  partial: "#d97706",
  understood: "#22c55e",
};

const nodeTypes: NodeTypes = {};

const NODE_W = 260;
const NODE_H = 100;
const COLS = 3;
const GAP_X = 60;
const GAP_Y = 60;

function isPrerequisiteNode(nodeId: string, edges: GraphEdge[]): boolean {
  return edges.some((e) => e.to_id === nodeId && e.kind === "prerequisite");
}

function toRFNodes(nodes: GraphNode[], edges: GraphEdge[]): Node[] {
  return nodes.map((n, i) => {
    const isPrereq = isPrerequisiteNode(n.id, edges);
    const isWeak = n.weak_spot;
    const col = i % COLS;
    const row = Math.floor(i / COLS);

    return {
      id: n.id,
      position: { x: col * (NODE_W + GAP_X), y: row * (NODE_H + GAP_Y) },
      data: {
        label: (
          <div style={{ textAlign: "left", padding: "4px 2px" }}>
            <div style={{ display: "flex", gap: 6, marginBottom: 4, flexWrap: "wrap" }}>
              {isPrereq && (
                <span style={{ fontSize: 10, background: "#4c1d95", color: "#c4b5fd", borderRadius: 4, padding: "1px 6px" }}>
                  added during learning
                </span>
              )}
              {isWeak && (
                <span style={{ fontSize: 10, background: "#7f1d1d", color: "#fca5a5", borderRadius: 4, padding: "1px 6px" }}>
                  weak spot
                </span>
              )}
            </div>
            <div style={{ fontWeight: 700, fontSize: 13, lineHeight: 1.3, color: "#f9fafb" }}>
              {n.title}
            </div>
            <div style={{ fontSize: 11, color: "#9ca3af", fontFamily: "monospace", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {n.file}
            </div>
          </div>
        ),
      },
      style: {
        background: stateColor[n.understanding_state] ?? stateColor.not_started,
        border: isWeak
          ? "2px solid #ef4444"
          : isPrereq
          ? "2px dashed #7c3aed"
          : `2px solid ${stateBorder[n.understanding_state] ?? "#6b7280"}`,
        borderRadius: 10,
        width: NODE_W,
        height: NODE_H,
        boxShadow: isWeak ? "0 0 12px #ef444440" : undefined,
      },
    };
  });
}

function toRFEdges(edges: GraphEdge[]): Edge[] {
  return edges.map((e, i) => ({
    id: `e-${i}`,
    source: e.from_id,
    target: e.to_id,
    style: {
      stroke: e.kind === "prerequisite" ? "#7c3aed" : "#4b5563",
      strokeWidth: 2,
      strokeDasharray: e.kind === "prerequisite" ? "5,4" : undefined,
    },
  }));
}

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export default function JourneyGraph({ nodes, edges }: Props) {
  const rfNodes = toRFNodes(nodes, edges);
  const rfEdges = toRFEdges(edges);

  const understood = nodes.filter((n) => n.understanding_state === "understood").length;
  const partial = nodes.filter((n) => n.understanding_state === "partial").length;
  const wrong = nodes.filter((n) => n.understanding_state === "failed").length;
  const weak = nodes.filter((n) => n.weak_spot).length;
  const added = nodes.filter((n) => isPrerequisiteNode(n.id, edges)).length;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", gap: 12 }}>
      {/* Stats */}
      <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
        <Stat label="Understood" value={understood} color="#22c55e" />
        <Stat label="Partial" value={partial} color="#d97706" />
        <Stat label="Wrong" value={wrong} color="#ef4444" />
        <Stat label="Weak spots" value={weak} color="#f87171" />
        <Stat label="Added during learning" value={added} color="#7c3aed" />
      </div>

      {/* Graph */}
      <div style={{ flex: 1, borderRadius: 12, overflow: "hidden", border: "1px solid #1f2937", minHeight: 0 }}>
        <ReactFlow
          nodes={rfNodes}
          edges={rfEdges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          panOnDrag={false}
          zoomOnScroll={false}
          zoomOnPinch={false}
          zoomOnDoubleClick={false}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          attributionPosition="bottom-right"
        >
          <Background color="#1f2937" gap={20} />
        </ReactFlow>
      </div>

      {/* Legend */}
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        <LegendItem color="#14532d" border="#22c55e" label="Understood" />
        <LegendItem color="#92400e" border="#d97706" label="Partial" />
        <LegendItem color="#7f1d1d" border="#ef4444" label="Wrong" />
        <LegendItem color="#374151" border="#6b7280" label="Not visited" />
        <LegendItem color="#374151" border="#7c3aed" dashed label="Added during learning" />
        <LegendItem color="#374151" border="#f87171" label="Weak spot" />
      </div>
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
      <span style={{ fontSize: 22, fontWeight: 700, color }}>{value}</span>
      <span style={{ fontSize: 11, color: "#9ca3af" }}>{label}</span>
    </div>
  );
}

function LegendItem({ color, border, dashed, label }: { color: string; border: string; dashed?: boolean; label: string }) {
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#9ca3af" }}>
      <span style={{
        display: "inline-block", width: 12, height: 12, borderRadius: 3,
        background: color,
        border: `2px ${dashed ? "dashed" : "solid"} ${border}`,
      }} />
      {label}
    </span>
  );
}
