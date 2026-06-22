import { useState, useRef, useCallback, useMemo, useEffect } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Crosshair, Globe, Search, Target } from 'lucide-react';
import { useVault } from '../context/VaultContext';
import { graph as graphApi } from '../api';

// ── Visual constants ──────────────────────────────────────────────────────────

const NODE_CONFIG = {
  character: { color: '#a78bfa', label: 'Characters' },
  location:  { color: '#34d399', label: 'Locations'  },
  note:      { color: '#60a5fa', label: 'Notes'      },
};
const ALL_NODE_TYPES = Object.keys(NODE_CONFIG);

const EDGE_PALETTE = [
  '#a78bfa', '#f472b6', '#ef4444', '#f59e0b',
  '#10b981', '#60a5fa', '#34d399', '#fb923c',
  '#e879f9', '#facc15', '#818cf8', '#94a3b8',
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function hashIdx(str, len) {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = str.charCodeAt(i) + ((h << 5) - h);
  return Math.abs(h) % len;
}

function edgeColor(type) {
  return EDGE_PALETTE[hashIdx(type || '', EDGE_PALETTE.length)];
}

function nodeRadius(connectionCount) {
  return Math.sqrt(connectionCount || 0) * 4 + 6;
}

function entityPath(node) {
  if (node.type === 'character') return '/characters';
  if (node.type === 'location') return '/maps';
  return `/browse?note=${node.id}`;
}

// ── Canvas draw helpers ───────────────────────────────────────────────────────

function drawDiamond(ctx, cx, cy, r) {
  ctx.beginPath();
  ctx.moveTo(cx, cy - r);
  ctx.lineTo(cx + r, cy);
  ctx.lineTo(cx, cy + r);
  ctx.lineTo(cx - r, cy);
  ctx.closePath();
}

function drawRoundedRect(ctx, x, y, w, h, rad) {
  ctx.beginPath();
  ctx.moveTo(x + rad, y);
  ctx.lineTo(x + w - rad, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + rad);
  ctx.lineTo(x + w, y + h - rad);
  ctx.quadraticCurveTo(x + w, y + h, x + w - rad, y + h);
  ctx.lineTo(x + rad, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - rad);
  ctx.lineTo(x, y + rad);
  ctx.quadraticCurveTo(x, y, x + rad, y);
  ctx.closePath();
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function Graph() {
  const { activeVaultId } = useVault();
  const navigate = useNavigate();
  const graphRef = useRef(null);

  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [search, setSearch] = useState('');
  const [hiddenNodeTypes, setHiddenNodeTypes] = useState(new Set());
  const [hiddenRelTypes, setHiddenRelTypes] = useState(new Set());
  const [isLocalMode, setIsLocalMode] = useState(false);
  const [localNodeId, setLocalNodeId] = useState(null);
  const [hoveredNode, setHoveredNode] = useState(null);
  const [hoverPos, setHoverPos] = useState({ x: 0, y: 0 });
  const [selectedNodeId, setSelectedNodeId] = useState(null);

  // Reset cursor on unmount to prevent it getting stuck when navigating away
  useEffect(() => {
    return () => { document.body.style.cursor = 'default'; };
  }, []);

  // ── Data ────────────────────────────────────────────────────────────────────

  const { data: fullData, isLoading: fullLoading } = useQuery({
    queryKey: ['vault-graph', activeVaultId],
    queryFn: () => graphApi.full(activeVaultId),
    enabled: !!activeVaultId,
    staleTime: 30_000,
  });

  const { data: localData, isLoading: localLoading } = useQuery({
    queryKey: ['vault-graph-node', activeVaultId, localNodeId],
    queryFn: () => graphApi.node(activeVaultId, localNodeId),
    enabled: !!activeVaultId && !!localNodeId && isLocalMode,
    staleTime: 30_000,
  });

  const rawData = isLocalMode && localData ? localData : fullData;
  const isLoading = fullLoading || (isLocalMode && localLoading);

  const allRelTypes = useMemo(() => {
    if (!rawData?.edges) return [];
    return [...new Set(rawData.edges.map(e => e.type).filter(Boolean))].sort();
  }, [rawData]);

  // ── Filtered data passed to graph ────────────────────────────────────────────

  const graphData = useMemo(() => {
    if (!rawData) return { nodes: [], links: [] };
    const lowerSearch = search.toLowerCase();

    const nodes = rawData.nodes
      .filter(n => !hiddenNodeTypes.has(n.type))
      .map(n => ({
        ...n,
        __dimmed: lowerSearch ? !n.title.toLowerCase().includes(lowerSearch) : false,
        __selected: n.id === selectedNodeId,
      }));

    const nodeIds = new Set(nodes.map(n => n.id));

    const links = rawData.edges
      .filter(e =>
        nodeIds.has(e.source) &&
        nodeIds.has(e.target) &&
        !hiddenRelTypes.has(e.type)
      )
      .map(e => ({ ...e }));

    return { nodes, links };
  }, [rawData, hiddenNodeTypes, hiddenRelTypes, search, selectedNodeId]);

  // ── Canvas renderers ─────────────────────────────────────────────────────────

  const nodeCanvasObject = useCallback((node, ctx, globalScale) => {
    const r = nodeRadius(node.connection_count);
    const cfg = NODE_CONFIG[node.type] || NODE_CONFIG.note;

    ctx.globalAlpha = node.__dimmed ? 0.12 : 0.92;

    if (node.type === 'character') {
      ctx.beginPath();
      ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
    } else if (node.type === 'location') {
      drawDiamond(ctx, node.x, node.y, r * 1.15);
    } else {
      drawRoundedRect(ctx, node.x - r, node.y - r * 0.72, r * 2, r * 1.44, 3);
    }

    ctx.fillStyle = cfg.color;
    ctx.fill();

    if (node.__selected) {
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 2.5 / globalScale;
      ctx.stroke();
    }

    const fontSize = Math.max(4, Math.min(9, r * 0.65)) / globalScale;
    if (fontSize * globalScale >= 4.5) {
      ctx.font = `${fontSize}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = 'rgba(255,255,255,0.93)';
      const maxChars = Math.max(6, Math.floor(r * 1.6));
      const lbl = node.title.length > maxChars ? node.title.slice(0, maxChars) + '…' : node.title;
      ctx.fillText(lbl, node.x, node.y);
    }

    ctx.globalAlpha = 1;
  }, []);

  const nodePointerAreaPaint = useCallback((node, color, ctx) => {
    ctx.fillStyle = color;
    const r = nodeRadius(node.connection_count) + 4;
    ctx.beginPath();
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
    ctx.fill();
  }, []);

  const linkCanvasObject = useCallback((link, ctx, globalScale) => {
    if (globalScale < 1.5) return;
    const start = link.source;
    const end = link.target;
    if (!start || !end || typeof start !== 'object') return;
    const label = link.label || link.type;
    if (!label) return;

    const midX = (start.x + end.x) / 2;
    const midY = (start.y + end.y) / 2;
    const fontSize = 7 / globalScale;
    ctx.globalAlpha = 0.72;
    ctx.font = `${fontSize}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = edgeColor(link.type);
    ctx.fillText(label, midX, midY - 2 / globalScale);
    ctx.globalAlpha = 1;
  }, []);

  // ── Event handlers ───────────────────────────────────────────────────────────

  const handleNodeClick = useCallback((node) => {
    setSelectedNodeId(node.id);
    if (isLocalMode) {
      setLocalNodeId(node.id);
    } else {
      document.body.style.cursor = 'default';
      navigate(entityPath(node));
    }
  }, [isLocalMode, navigate]);

  const handleNodeHover = useCallback((node) => {
    setHoveredNode(node || null);
    document.body.style.cursor = node ? 'pointer' : 'default';
  }, []);

  const handleMouseMove = useCallback((e) => {
    if (hoveredNode) setHoverPos({ x: e.clientX, y: e.clientY });
  }, [hoveredNode]);

  const handleZoomFit = useCallback(() => {
    graphRef.current?.zoomToFit(400, 40);
  }, []);

  const handleSearchEnter = useCallback((e) => {
    if (e.key !== 'Enter' || !search) return;
    const match = graphData.nodes.find(n =>
      n.title.toLowerCase().includes(search.toLowerCase())
    );
    if (match && graphRef.current) {
      graphRef.current.centerAt(match.x, match.y, 600);
      graphRef.current.zoom(2.5, 600);
      setSelectedNodeId(match.id);
    }
  }, [search, graphData.nodes]);

  const toggleNodeType = useCallback((type) => {
    setHiddenNodeTypes(prev => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type); else next.add(type);
      return next;
    });
  }, []);

  const toggleRelType = useCallback((type) => {
    setHiddenRelTypes(prev => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type); else next.add(type);
      return next;
    });
  }, []);

  const enterLocalMode = useCallback((nodeId) => {
    setIsLocalMode(true);
    setLocalNodeId(nodeId);
    setSelectedNodeId(nodeId);
  }, []);

  const exitLocalMode = useCallback(() => {
    setIsLocalMode(false);
    setLocalNodeId(null);
    setSelectedNodeId(null);
  }, []);

  // ── Early returns ────────────────────────────────────────────────────────────

  if (!activeVaultId) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-txt-muted text-sm">Select a vault to view the graph.</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center space-y-3">
          <div
            className="w-8 h-8 rounded-full animate-spin mx-auto"
            style={{ border: '2px solid rgba(124,92,252,0.2)', borderTopColor: '#7c5cfc' }}
          />
          <p className="text-txt-muted text-sm">Weaving the world graph…</p>
        </div>
      </div>
    );
  }

  if (!rawData || rawData.nodes.length === 0) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center space-y-4 max-w-sm px-4">
          <div className="text-5xl">🕸️</div>
          <h2 className="text-xl font-bold text-txt">No entities yet</h2>
          <p className="text-txt-muted text-sm">
            Add notes, characters, or maps to your vault — they&apos;ll appear here as a knowledge graph.
          </p>
          <button
            onClick={() => navigate('/browse')}
            className="px-6 py-2.5 bg-accent text-white rounded-xl font-medium hover:opacity-90 transition text-sm"
          >
            Go to Browse
          </button>
        </div>
      </div>
    );
  }

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="relative w-full h-full overflow-hidden bg-base" onMouseMove={handleMouseMove}>

      {/* ── Left filter sidebar ──────────────────────────────────────────────── */}
      <div
        className="absolute top-0 left-0 h-full z-10 flex"
        style={{ transition: 'width 200ms ease' }}
      >
        <div
          className="h-full bg-surface border-r border-border-subtle flex flex-col overflow-hidden"
          style={{ width: sidebarOpen ? 272 : 0, transition: 'width 200ms ease', overflow: 'hidden' }}
        >
          {sidebarOpen && (
            <div className="flex flex-col gap-4 p-4 overflow-y-auto flex-1 min-h-0">
              {/* Search */}
              <div>
                <p className="text-[10px] uppercase tracking-widest text-txt-muted font-bold mb-2">Search</p>
                <div className="relative">
                  <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-txt-muted" />
                  <input
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    onKeyDown={handleSearchEnter}
                    placeholder="Find node… (Enter to center)"
                    className="w-full bg-elevated border border-border-subtle rounded-lg pl-8 pr-3 py-1.5 text-sm text-txt placeholder:text-txt-muted focus:border-accent focus:outline-none"
                  />
                  {search && (
                    <button
                      onClick={() => setSearch('')}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-txt-muted hover:text-txt"
                    >
                      ×
                    </button>
                  )}
                </div>
              </div>

              {/* Entity types */}
              <div>
                <p className="text-[10px] uppercase tracking-widest text-txt-muted font-bold mb-2">Entity Types</p>
                <div className="flex flex-col gap-1.5">
                  {ALL_NODE_TYPES.map(type => {
                    const cfg = NODE_CONFIG[type];
                    const isHidden = hiddenNodeTypes.has(type);
                    const count = rawData?.nodes?.filter(n => n.type === type).length || 0;
                    return (
                      <label key={type} className="flex items-center gap-2.5 cursor-pointer group">
                        <div
                          className="w-4 h-4 rounded border-2 flex-shrink-0 flex items-center justify-center transition-all"
                          style={{
                            borderColor: cfg.color,
                            backgroundColor: isHidden ? 'transparent' : cfg.color,
                          }}
                          onClick={() => toggleNodeType(type)}
                        >
                          {!isHidden && (
                            <svg viewBox="0 0 10 8" width="8" height="8" fill="white">
                              <polyline points="1,4 4,7 9,1" strokeWidth="1.5" stroke="white" fill="none" strokeLinecap="round" strokeLinejoin="round" />
                            </svg>
                          )}
                        </div>
                        <span
                          className="text-sm flex-1 transition-colors"
                          style={{ color: isHidden ? 'var(--txt-muted)' : 'var(--txt)' }}
                          onClick={() => toggleNodeType(type)}
                        >
                          {cfg.label}
                        </span>
                        <span className="text-xs text-txt-muted">{count}</span>
                      </label>
                    );
                  })}
                </div>
              </div>

              {/* Relationship types */}
              {allRelTypes.length > 0 && (
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-[10px] uppercase tracking-widest text-txt-muted font-bold">Relationships</p>
                    {hiddenRelTypes.size > 0 && (
                      <button
                        onClick={() => setHiddenRelTypes(new Set())}
                        className="text-[10px] text-accent hover:underline"
                      >
                        Show all
                      </button>
                    )}
                  </div>
                  <div className="flex flex-col gap-1">
                    {allRelTypes.map(type => {
                      const isHidden = hiddenRelTypes.has(type);
                      const color = edgeColor(type);
                      const count = rawData?.edges?.filter(e => e.type === type).length || 0;
                      return (
                        <label key={type} className="flex items-center gap-2 cursor-pointer" onClick={() => toggleRelType(type)}>
                          <span
                            className="inline-block w-3 h-0.5 flex-shrink-0 rounded transition-opacity"
                            style={{ backgroundColor: color, opacity: isHidden ? 0.2 : 1 }}
                          />
                          <span
                            className="text-xs flex-1 truncate transition-colors"
                            style={{ color: isHidden ? 'var(--txt-muted)' : 'var(--txt)' }}
                          >
                            {type}
                          </span>
                          <span className="text-[10px] text-txt-muted">{count}</span>
                        </label>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Stats */}
              <div className="mt-auto pt-3 border-t border-border-subtle text-xs text-txt-muted space-y-0.5">
                <p>{graphData.nodes.length} nodes · {graphData.links.length} edges</p>
                {isLocalMode && (
                  <p className="text-accent text-[11px]">Local view active</p>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Sidebar toggle button */}
        <button
          onClick={() => setSidebarOpen(o => !o)}
          className="absolute top-1/2 -translate-y-1/2 -right-3.5 w-7 h-7 bg-surface border border-border-subtle rounded-full flex items-center justify-center shadow-sm hover:bg-hover transition z-20"
          title={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
        >
          {sidebarOpen ? <ChevronLeft size={13} /> : <ChevronRight size={13} />}
        </button>
      </div>

      {/* ── Top-right controls ───────────────────────────────────────────────── */}
      <div className="absolute top-4 right-4 z-10 flex items-center gap-2">
        {/* Local mode toggle */}
        <button
          onClick={isLocalMode ? exitLocalMode : () => {
            if (selectedNodeId) enterLocalMode(selectedNodeId);
          }}
          disabled={!isLocalMode && !selectedNodeId}
          className={[
            'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition',
            isLocalMode
              ? 'bg-accent text-white border-accent'
              : 'bg-surface border-border-subtle text-txt-dim hover:text-txt hover:bg-hover disabled:opacity-40 disabled:cursor-not-allowed',
          ].join(' ')}
          title={isLocalMode ? 'Back to full graph' : 'View local neighborhood of selected node'}
        >
          {isLocalMode ? <Globe size={13} /> : <Target size={13} />}
          {isLocalMode ? 'Full graph' : 'Local view'}
        </button>

        {/* 3D toggle — coming soon */}
        <button
          disabled
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-border-subtle bg-surface text-txt-muted opacity-50 cursor-not-allowed"
          title="3D mode — coming soon"
        >
          3D
        </button>

        {/* Zoom to fit */}
        <button
          onClick={handleZoomFit}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-border-subtle bg-surface text-txt-dim hover:text-txt hover:bg-hover transition"
          title="Zoom to fit"
        >
          <Crosshair size={13} />
          Fit
        </button>
      </div>

      {/* ── Local mode banner ────────────────────────────────────────────────── */}
      {isLocalMode && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10 bg-accent/90 text-white text-xs px-4 py-1.5 rounded-full font-medium shadow-lg">
          Local view — click a node to explore its neighborhood
        </div>
      )}

      {/* ── Graph canvas ─────────────────────────────────────────────────────── */}
      <div className="w-full h-full">
        <ForceGraph2D
          ref={graphRef}
          graphData={graphData}
          nodeId="id"
          nodeCanvasObject={nodeCanvasObject}
          nodeCanvasObjectMode="replace"
          nodePointerAreaPaint={nodePointerAreaPaint}
          linkColor={link => edgeColor(link.type)}
          linkOpacity={0.45}
          linkWidth={1.2}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={0.85}
          linkDirectionalArrowColor={link => edgeColor(link.type)}
          linkCanvasObject={linkCanvasObject}
          linkCanvasObjectMode={() => 'after'}
          onNodeClick={handleNodeClick}
          onNodeHover={handleNodeHover}
          onBackgroundClick={() => setSelectedNodeId(null)}
          cooldownTicks={120}
          d3AlphaDecay={0.02}
          d3VelocityDecay={0.25}
          enableNodeDrag
          enableZoomInteraction
          backgroundColor="transparent"
        />
      </div>

      {/* ── Hover card ───────────────────────────────────────────────────────── */}
      {hoveredNode && (
        <div
          className="fixed z-30 pointer-events-none max-w-[220px] bg-card border border-border-subtle rounded-xl px-3.5 py-2.5 shadow-xl"
          style={{ left: hoverPos.x + 16, top: hoverPos.y - 12 }}
        >
          <div className="flex items-center gap-2 mb-1">
            <span
              className="inline-block w-2 h-2 rounded-full flex-shrink-0"
              style={{ backgroundColor: (NODE_CONFIG[hoveredNode.type] || NODE_CONFIG.note).color }}
            />
            <span className="text-[10px] uppercase tracking-wider text-txt-muted font-semibold">
              {hoveredNode.type}
            </span>
          </div>
          <p className="text-sm font-semibold text-txt leading-tight mb-1">{hoveredNode.title}</p>
          {hoveredNode.content_preview && (
            <p className="text-xs text-txt-muted leading-relaxed line-clamp-3">
              {hoveredNode.content_preview}
            </p>
          )}
          <p className="text-[10px] text-txt-muted mt-1.5 opacity-60">
            {hoveredNode.connection_count} connection{hoveredNode.connection_count !== 1 ? 's' : ''} · click to open
          </p>
        </div>
      )}
    </div>
  );
}
