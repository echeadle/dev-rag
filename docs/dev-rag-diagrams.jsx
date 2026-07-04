import { useState } from "react";

// ── Design tokens ────────────────────────────────────────────────────────────
// Palette drawn from terminal/DevOps aesthetic: near-black ground, amber
// signal colour, cool slate for infrastructure, muted teal for data stores.
const C = {
  bg:        "#0f1117",
  surface:   "#181c27",
  border:    "#252a38",
  amber:     "#f5a623",
  amberDim:  "#7a5112",
  teal:      "#2dd4bf",
  tealDim:   "#134e4a",
  slate:     "#94a3b8",
  slateLight:"#cbd5e1",
  purple:    "#a78bfa",
  purpleDim: "#3b2f6e",
  green:     "#4ade80",
  greenDim:  "#14532d",
  red:       "#f87171",
  redDim:    "#4c1d1d",
  text:      "#e2e8f0",
  textDim:   "#64748b",
};

// ── Shared primitives ────────────────────────────────────────────────────────
const Box = ({ x, y, w, h, fill, stroke, rx = 6, children, style = {} }) => (
  <g>
    <rect x={x} y={y} width={w} height={h} rx={rx}
      fill={fill} stroke={stroke} strokeWidth={1.5} style={style} />
    {children}
  </g>
);

const Label = ({ x, y, text, size = 12, color = C.text, weight = "500", anchor = "middle" }) => (
  <text x={x} y={y} textAnchor={anchor} dominantBaseline="middle"
    fontSize={size} fontFamily="'JetBrains Mono', 'Fira Code', monospace"
    fontWeight={weight} fill={color}>
    {text}
  </text>
);

const Sub = ({ x, y, text, color = C.textDim }) => (
  <text x={x} y={y} textAnchor="middle" dominantBaseline="middle"
    fontSize={9.5} fontFamily="'JetBrains Mono', 'Fira Code', monospace"
    fontWeight="400" fill={color}>
    {text}
  </text>
);

// Arrow with optional label
const Arrow = ({ x1, y1, x2, y2, color = C.slate, label = "", dash = false }) => {
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const len = 9;
  const ax = x2 - len * Math.cos(angle - 0.4);
  const ay = y2 - len * Math.sin(angle - 0.4);
  const bx = x2 - len * Math.cos(angle + 0.4);
  const by = y2 - len * Math.sin(angle + 0.4);
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  return (
    <g>
      <line x1={x1} y1={y1} x2={x2} y2={y2}
        stroke={color} strokeWidth={1.5}
        strokeDasharray={dash ? "5 3" : "none"} />
      <polygon points={`${x2},${y2} ${ax},${ay} ${bx},${by}`} fill={color} />
      {label && (
        <text x={mx} y={my - 7} textAnchor="middle" fontSize={9}
          fontFamily="'JetBrains Mono', 'Fira Code', monospace"
          fill={color} fontWeight="500">
          {label}
        </text>
      )}
    </g>
  );
};

// ── DIAGRAM 1: Ingest Pipeline ───────────────────────────────────────────────
const IngestDiagram = () => {
  const W = 700, H = 320;

  const nodes = [
    { id: "src",    x: 30,  y: 130, w: 90,  h: 60, fill: C.surface, stroke: C.purple,    label: "Sources",   sub: "PDFs / URLs" },
    { id: "loader", x: 160, y: 130, w: 100, h: 60, fill: C.surface, stroke: C.amber,     label: "Loader",    sub: "PyMuPDF / httpx" },
    { id: "chunk",  x: 300, y: 130, w: 100, h: 60, fill: C.surface, stroke: C.amber,     label: "Chunker",   sub: "sliding window" },
    { id: "embed",  x: 440, y: 130, w: 100, h: 60, fill: C.surface, stroke: C.teal,      label: "Embedder",  sub: "BGE-M3" },
    { id: "store",  x: 580, y: 100, w: 100, h: 60, fill: C.tealDim, stroke: C.teal,      label: "ChromaDB",  sub: "vectors" },
    { id: "meta",   x: 580, y: 180, w: 100, h: 60, fill: C.purpleDim,stroke: C.purple,   label: "SQLite",    sub: "metadata" },
    { id: "head",   x: 300, y: 240, w: 100, h: 50, fill: C.redDim,  stroke: C.red,       label: "Headroom",  sub: "compress" },
  ];

  const arrows = [
    { x1: 120, y1: 160, x2: 157, y2: 160, color: C.purple,  label: "" },
    { x1: 260, y1: 160, x2: 297, y2: 160, color: C.amber,   label: "text" },
    { x1: 400, y1: 160, x2: 437, y2: 160, color: C.amber,   label: "chunks" },
    { x1: 540, y1: 148, x2: 577, y2: 135, color: C.teal,    label: "embed" },
    { x1: 540, y1: 172, x2: 577, y2: 205, color: C.purple,  label: "meta" },
    // Headroom optional path
    { x1: 350, y1: 190, x2: 350, y2: 237, color: C.red,     label: "", dash: true },
    { x1: 400, y1: 265, x2: 437, y2: 178, color: C.red,     label: "→ embed", dash: true },
  ];

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", background: C.bg, borderRadius: 10 }}>
      {/* Title */}
      <text x={W / 2} y={28} textAnchor="middle" fontSize={13} fontWeight="700"
        fontFamily="'JetBrains Mono', monospace" fill={C.amber} letterSpacing="1">
        INGEST PIPELINE
      </text>
      <text x={W / 2} y={46} textAnchor="middle" fontSize={10}
        fontFamily="'JetBrains Mono', monospace" fill={C.textDim}>
        documents → vectors + metadata
      </text>

      {/* Step numbers */}
      {[{ x: 75, label: "①" }, { x: 210, label: "②" }, { x: 350, label: "③" }, { x: 490, label: "④" }].map((s, i) => (
        <text key={i} x={s.x} y={105} textAnchor="middle" fontSize={11}
          fontFamily="'JetBrains Mono', monospace" fill={C.textDim}>{s.label}</text>
      ))}

      {/* Arrows */}
      {arrows.map((a, i) => <Arrow key={i} {...a} />)}

      {/* Nodes */}
      {nodes.map(n => (
        <Box key={n.id} x={n.x} y={n.y} w={n.w} h={n.h} fill={n.fill} stroke={n.stroke}>
          <Label x={n.x + n.w / 2} y={n.y + n.h / 2 - 8} text={n.label} size={11} color={n.stroke} weight="700" />
          <Sub   x={n.x + n.w / 2} y={n.y + n.h / 2 + 9} text={n.sub} />
        </Box>
      ))}

      {/* Headroom label */}
      <text x={350} y={307} textAnchor="middle" fontSize={9}
        fontFamily="'JetBrains Mono', monospace" fill={C.red}>
        optional: pre-compress chunks before embedding
      </text>

      {/* Legend */}
      <rect x={22} y={285} width={8} height={8} fill={C.tealDim} stroke={C.teal} strokeWidth={1} rx={1} />
      <text x={34} y={291} fontSize={9} fontFamily="'JetBrains Mono', monospace" fill={C.slateLight} dominantBaseline="middle">vector store</text>
      <rect x={95} y={285} width={8} height={8} fill={C.purpleDim} stroke={C.purple} strokeWidth={1} rx={1} />
      <text x={107} y={291} fontSize={9} fontFamily="'JetBrains Mono', monospace" fill={C.slateLight} dominantBaseline="middle">metadata store</text>
      <line x1={185} y1={289} x2={205} y2={289} stroke={C.red} strokeWidth={1.5} strokeDasharray="4 2" />
      <text x={210} y={291} fontSize={9} fontFamily="'JetBrains Mono', monospace" fill={C.slateLight} dominantBaseline="middle">optional Headroom path</text>
    </svg>
  );
};

// ── DIAGRAM 2: Query Pipeline ────────────────────────────────────────────────
const QueryDiagram = () => {
  const W = 700, H = 380;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", background: C.bg, borderRadius: 10 }}>
      {/* Title */}
      <text x={W / 2} y={28} textAnchor="middle" fontSize={13} fontWeight="700"
        fontFamily="'JetBrains Mono', monospace" fill={C.teal} letterSpacing="1">
        QUERY PIPELINE
      </text>
      <text x={W / 2} y={46} textAnchor="middle" fontSize={10}
        fontFamily="'JetBrains Mono', monospace" fill={C.textDim}>
        Claude Code → MCP → FastAPI → vector search → compressed results
      </text>

      {/* ── Row 1: Claude Code → MCP Server ── */}
      {/* Claude Code */}
      <Box x={20} y={80} w={110} h={60} fill={C.surface} stroke={C.amber}>
        <Label x={75} y={103} text="Claude Code" size={10} color={C.amber} weight="700" />
        <Sub   x={75} y={120} text="terminal session" />
      </Box>

      {/* MCP Server */}
      <Box x={170} y={80} w={110} h={60} fill={C.surface} stroke={C.green}>
        <Label x={225} y={103} text="MCP Server" size={10} color={C.green} weight="700" />
        <Sub   x={225} y={120} text="mcp_server.py" />
      </Box>

      {/* FastAPI */}
      <Box x={320} y={80} w={110} h={60} fill={C.surface} stroke={C.amber}>
        <Label x={375} y={103} text="FastAPI" size={10} color={C.amber} weight="700" />
        <Sub   x={375} y={120} text="dev-rag API" />
      </Box>

      {/* Embedder */}
      <Box x={470} y={80} w={110} h={60} fill={C.surface} stroke={C.teal}>
        <Label x={525} y={103} text="Embedder" size={10} color={C.teal} weight="700" />
        <Sub   x={525} y={120} text="BGE-M3" />
      </Box>

      {/* Row 1 arrows (query flow →) */}
      <Arrow x1={130} y1={110} x2={167} y2={110} color={C.green}  label="tool call" />
      <Arrow x1={280} y1={110} x2={317} y2={110} color={C.amber}  label="POST /search" />
      <Arrow x1={430} y1={110} x2={467} y2={110} color={C.teal}   label="query text" />

      {/* ── Row 2: Stores ── */}
      {/* ChromaDB */}
      <Box x={470} y={200} w={110} h={55} fill={C.tealDim} stroke={C.teal}>
        <Label x={525} y={220} text="ChromaDB" size={10} color={C.teal} weight="700" />
        <Sub   x={525} y={237} text="ANN search" />
      </Box>

      {/* SQLite */}
      <Box x={320} y={200} w={110} h={55} fill={C.purpleDim} stroke={C.purple}>
        <Label x={375} y={220} text="SQLite" size={10} color={C.purple} weight="700" />
        <Sub   x={375} y={237} text="doc metadata" />
      </Box>

      {/* embed → chroma */}
      <Arrow x1={525} y1={140} x2={525} y2={197} color={C.teal} label="query vector" />
      {/* chroma → sqlite (join on doc_id) */}
      <Arrow x1={467} y1={227} x2={433} y2={227} color={C.purple} label="doc_id join" />

      {/* SQLite → FastAPI (merged results) */}
      <Arrow x1={375} y1={200} x2={375} y2={143} color={C.purple} label="merged chunks" />

      {/* ── Headroom ── */}
      <Box x={320} y={305} w={110} h={50} fill={C.redDim} stroke={C.red}>
        <Label x={375} y={324} text="Headroom" size={10} color={C.red} weight="700" />
        <Sub   x={375} y={341} text="CCR compress" />
      </Box>

      {/* FastAPI → Headroom */}
      <Arrow x1={375} y1={140} x2={375} y2={302} color={C.red} label="raw chunks" dash />

      {/* Headroom → MCP */}
      <Arrow x1={320} y1={330} x2={280} y2={130} color={C.red} label="compressed" dash />

      {/* ── Return path (no Headroom) ── */}
      {/* FastAPI → MCP (direct return, no Headroom) */}
      <Arrow x1={317} y1={95} x2={283} y2={95} color={C.green} label="chunks" />

      {/* MCP → Claude Code */}
      <Arrow x1={167} y1={110} x2={130} y2={110} color={C.green} label="TextContent" />

      {/* ── Labels ── */}
      <text x={350} y={368} textAnchor="middle" fontSize={9}
        fontFamily="'JetBrains Mono', monospace" fill={C.red}>
        dashed = optional Headroom compression path
      </text>

      {/* Legend */}
      <rect x={22} y={355} width={8} height={8} fill="none" stroke={C.green} strokeWidth={1.5} rx={1} />
      <text x={34} y={361} fontSize={9} fontFamily="'JetBrains Mono', monospace" fill={C.slateLight} dominantBaseline="middle">query flow</text>
      <rect x={90} y={355} width={8} height={8} fill={C.tealDim} stroke={C.teal} strokeWidth={1} rx={1} />
      <text x={102} y={361} fontSize={9} fontFamily="'JetBrains Mono', monospace" fill={C.slateLight} dominantBaseline="middle">vector store</text>
      <rect x={165} y={355} width={8} height={8} fill={C.purpleDim} stroke={C.purple} strokeWidth={1} rx={1} />
      <text x={177} y={361} fontSize={9} fontFamily="'JetBrains Mono', monospace" fill={C.slateLight} dominantBaseline="middle">metadata</text>
    </svg>
  );
};

// ── App shell ────────────────────────────────────────────────────────────────
export default function App() {
  const [active, setActive] = useState("both");

  return (
    <div style={{
      background: C.bg, minHeight: "100vh", padding: "24px 16px",
      fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
    }}>
      <h1 style={{
        textAlign: "center", color: C.amber, fontSize: 15, fontWeight: 700,
        letterSpacing: "2px", marginBottom: 6, textTransform: "uppercase",
      }}>
        dev-rag · data flow
      </h1>
      <p style={{ textAlign: "center", color: C.textDim, fontSize: 11, marginBottom: 24 }}>
        ingest pipeline + query pipeline
      </p>

      {/* Toggle */}
      <div style={{ display: "flex", justifyContent: "center", gap: 8, marginBottom: 24 }}>
        {[["both", "Both"], ["ingest", "Ingest only"], ["query", "Query only"]].map(([val, label]) => (
          <button key={val} onClick={() => setActive(val)} style={{
            padding: "5px 14px", fontSize: 10, fontFamily: "inherit",
            border: `1px solid ${active === val ? C.amber : C.border}`,
            background: active === val ? C.amberDim : C.surface,
            color: active === val ? C.amber : C.textDim,
            borderRadius: 4, cursor: "pointer", letterSpacing: "0.5px",
          }}>
            {label}
          </button>
        ))}
      </div>

      <div style={{ maxWidth: 700, margin: "0 auto", display: "flex", flexDirection: "column", gap: 20 }}>
        {(active === "both" || active === "ingest") && (
          <div>
            <p style={{ color: C.textDim, fontSize: 10, marginBottom: 8, letterSpacing: "0.5px" }}>
              ① INGEST — source documents enter, chunks + vectors are stored
            </p>
            <IngestDiagram />
          </div>
        )}
        {(active === "both" || active === "query") && (
          <div>
            <p style={{ color: C.textDim, fontSize: 10, marginBottom: 8, letterSpacing: "0.5px" }}>
              ② QUERY — Claude Code asks, compressed results come back
            </p>
            <QueryDiagram />
          </div>
        )}
      </div>

      {/* Key */}
      <div style={{
        maxWidth: 700, margin: "20px auto 0", padding: "12px 16px",
        background: C.surface, border: `1px solid ${C.border}`, borderRadius: 6,
      }}>
        <p style={{ color: C.textDim, fontSize: 10, marginBottom: 8, letterSpacing: "1px" }}>COMPONENT KEY</p>
        {[
          [C.amber,  "FastAPI dev-rag API + loader/chunker pipeline"],
          [C.teal,   "BGE-M3 embedder + ChromaDB vector store"],
          [C.purple, "SQLite metadata store (source, domain, page, chunk_id)"],
          [C.green,  "MCP Server — bridge between Claude Code and dev-rag"],
          [C.red,    "Headroom — optional CCR compression layer (dashed paths)"],
        ].map(([color, desc]) => (
          <div key={color} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
            <div style={{ width: 10, height: 10, borderRadius: 2, background: color, flexShrink: 0 }} />
            <span style={{ color: C.slateLight, fontSize: 10 }}>{desc}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
