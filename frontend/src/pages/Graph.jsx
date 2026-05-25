import { useEffect, useRef, useState, useCallback } from 'react';
import * as d3 from 'd3';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { notes as notesApi, relationships as relationshipsApi } from '../api';
import { useVault } from '../context/VaultContext';

// ── Helpers ───────────────────────────────────────────────────────────────────

const PALETTE = ['#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#60a5fa', '#a78bfa', '#34d399', '#fb923c'];

function hashColor(key) {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = key.charCodeAt(i) + ((h << 5) - h);
  return PALETTE[Math.abs(h) % PALETTE.length];
}

function nodeColor(note) {
  return hashColor(note.tags?.[0] || note.title || note.id);
}

function calcRadius(connCount) {
  return Math.max(10, Math.min(38, 10 + connCount * 5));
}

function truncate(str, maxLen) {
  if (!str) return '';
  return str.length > maxLen ? str.slice(0, maxLen) + '…' : str;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function Graph() {
  const { activeVaultId } = useVault();
  const navigate = useNavigate();

  const svgRef = useRef(null);
  const containerRef = useRef(null);
  const simulationRef = useRef(null);
  const zoomBehaviorRef = useRef(null);
  const svgSelRef = useRef(null);

  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [tooltip, setTooltip] = useState(null);

  const { data: allNotes = [], isLoading: notesLoading } = useQuery({
    queryKey: ['notes', activeVaultId],
    queryFn: () => notesApi.list('', '', activeVaultId),
    enabled: !!activeVaultId,
  });

  const { data: allRelationships = [], isLoading: relsLoading } = useQuery({
    queryKey: ['relationships', activeVaultId],
    queryFn: () => relationshipsApi.list(activeVaultId),
    enabled: !!activeVaultId,
  });

  const isLoading = notesLoading || relsLoading;
  const hasRelationships = allRelationships.length > 0;
  const categories = [...new Set(allRelationships.map(r => r.relationship_type).filter(Boolean))];

  // For stats display only (stable UI value, not used as effect dep)
  const filteredCount = categoryFilter
    ? allRelationships.filter(r => r.relationship_type === categoryFilter).length
    : allRelationships.length;

  // ── D3 graph setup ──────────────────────────────────────────────────────────

  useEffect(() => {
    if (isLoading || !svgRef.current || !containerRef.current || !hasRelationships) return;

    if (simulationRef.current) simulationRef.current.stop();

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const rect = containerRef.current.getBoundingClientRect();
    const width = rect.width || window.innerWidth - 250;
    const height = rect.height || window.innerHeight;

    // Compute filtered rels inside effect so deps stay stable
    const filteredRels = categoryFilter
      ? allRelationships.filter(r => r.relationship_type === categoryFilter)
      : allRelationships;

    // Copy node data so D3 can mutate without touching React Query cache
    const nodeData = allNotes.map(n => ({ ...n }));
    const nodeById = new Map(nodeData.map(n => [n.id, n]));

    // Connection counts for node sizing
    const connCount = new Map();
    filteredRels.forEach(r => {
      connCount.set(r.source_id, (connCount.get(r.source_id) || 0) + 1);
      connCount.set(r.target_id, (connCount.get(r.target_id) || 0) + 1);
    });

    const linkData = filteredRels
      .filter(r => nodeById.has(r.source_id) && nodeById.has(r.target_id))
      .map(r => ({ ...r, source: r.source_id, target: r.target_id }));

    // Arrowhead marker
    const defs = svg.append('defs');
    defs.append('marker')
      .attr('id', 'ws-arrow')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 24)
      .attr('refY', 0)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
        .attr('d', 'M0,-5L10,0L0,5')
        .attr('fill', '#7c5cfc')
        .attr('opacity', 0.7);

    const g = svg.append('g');

    // Zoom + pan
    const zoom = d3.zoom()
      .scaleExtent([0.05, 8])
      .on('zoom', event => g.attr('transform', event.transform));

    svg.call(zoom);
    zoomBehaviorRef.current = zoom;
    svgSelRef.current = svg;

    // Force simulation
    const simulation = d3.forceSimulation(nodeData)
      .force('link',
        d3.forceLink(linkData)
          .id(d => d.id)
          .distance(130)
          .strength(0.55)
      )
      .force('charge', d3.forceManyBody().strength(-320))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collide', d3.forceCollide().radius(d => calcRadius(connCount.get(d.id) || 0) + 10));

    simulationRef.current = simulation;

    // ── Edges ──────────────────────────────────────────────────────────────────

    const linkSel = g.append('g')
      .selectAll('line')
      .data(linkData)
      .join('line')
        .attr('stroke', '#7c5cfc')
        .attr('stroke-opacity', 0.35)
        .attr('stroke-width', d => Math.max(1, (d.weight || 1) * 1.5))
        .attr('marker-end', d => d.direction === 'unidirectional' ? 'url(#ws-arrow)' : null)
        .style('cursor', 'default')
        .on('mouseenter', (event, d) => {
          setTooltip({
            x: event.clientX,
            y: event.clientY,
            text: d.label || d.relationship_type || 'related',
          });
        })
        .on('mouseleave', () => setTooltip(null));

    // Edge type labels
    const linkLabelSel = g.append('g')
      .selectAll('text')
      .data(linkData)
      .join('text')
        .attr('text-anchor', 'middle')
        .attr('font-size', 9)
        .attr('fill', 'rgba(160,164,184,0.7)')
        .attr('pointer-events', 'none')
        .text(d => d.relationship_type || '');

    // ── Nodes ──────────────────────────────────────────────────────────────────

    const nodeSel = g.append('g')
      .selectAll('g')
      .data(nodeData)
      .join('g')
        .attr('class', 'node')
        .style('cursor', 'pointer')
        .call(
          d3.drag()
            .on('start', (event, d) => {
              if (!event.active) simulation.alphaTarget(0.3).restart();
              d.fx = d.x;
              d.fy = d.y;
            })
            .on('drag', (event, d) => {
              d.fx = event.x;
              d.fy = event.y;
            })
            .on('end', (event, d) => {
              if (!event.active) simulation.alphaTarget(0);
              d.fx = null;
              d.fy = null;
            })
        )
        .on('click', (event, d) => {
          event.stopPropagation();
          navigate(`/browse?note=${d.id}`);
        })
        .on('mouseenter', (event, d) => {
          setTooltip({ x: event.clientX, y: event.clientY, note: d });
          d3.select(event.currentTarget).select('circle')
            .attr('stroke', '#fff')
            .attr('stroke-width', 3)
            .attr('fill-opacity', 1);
        })
        .on('mouseleave', (event, d) => {
          setTooltip(null);
          d3.select(event.currentTarget).select('circle')
            .attr('stroke', 'rgba(255,255,255,0.15)')
            .attr('stroke-width', 2)
            .attr('fill-opacity', 0.85);
        });

    nodeSel.append('circle')
      .attr('r', d => calcRadius(connCount.get(d.id) || 0))
      .attr('fill', d => nodeColor(d))
      .attr('fill-opacity', 0.85)
      .attr('stroke', 'rgba(255,255,255,0.15)')
      .attr('stroke-width', 2);

    nodeSel.append('text')
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'central')
      .attr('font-size', d => Math.max(7, Math.min(11, calcRadius(connCount.get(d.id) || 0) * 0.55)))
      .attr('fill', 'rgba(255,255,255,0.92)')
      .attr('pointer-events', 'none')
      .text(d => truncate(d.title, 14));

    // Tick handler
    simulation.on('tick', () => {
      linkSel
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y);

      linkLabelSel
        .attr('x', d => (d.source.x + d.target.x) / 2)
        .attr('y', d => (d.source.y + d.target.y) / 2 - 4);

      nodeSel.attr('transform', d => `translate(${d.x},${d.y})`);
    });

    return () => simulation.stop();
  }, [allNotes, allRelationships, categoryFilter, isLoading, hasRelationships, navigate]);

  // ── Search highlighting ─────────────────────────────────────────────────────

  useEffect(() => {
    if (!svgRef.current) return;
    d3.select(svgRef.current).selectAll('.node').attr('opacity', d => {
      if (!search) return 1;
      return d?.title?.toLowerCase().includes(search.toLowerCase()) ? 1 : 0.1;
    });
  }, [search]);

  // ── Controls ────────────────────────────────────────────────────────────────

  const resetZoom = useCallback(() => {
    if (!zoomBehaviorRef.current || !svgSelRef.current) return;
    svgSelRef.current
      .transition()
      .duration(400)
      .call(zoomBehaviorRef.current.transform, d3.zoomIdentity);
  }, []);

  // ── Render ──────────────────────────────────────────────────────────────────

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
            style={{
              border: '2px solid rgba(124,92,252,0.2)',
              borderTopColor: 'rgb(124,92,252)',
            }}
          />
          <p className="text-txt-muted text-sm">Loading graph…</p>
        </div>
      </div>
    );
  }

  if (!hasRelationships) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center space-y-4 max-w-sm px-4">
          <div className="text-6xl">🕸️</div>
          <h2 className="text-xl font-bold text-txt">No relationships yet</h2>
          <p className="text-txt-muted text-sm">
            Add relationships between notes in Browse — they'll show up here as a visual graph.
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

  return (
    <div className="relative w-full h-full overflow-hidden bg-base">
      {/* Controls panel */}
      <div className="absolute top-4 left-4 z-10 w-52 bg-surface border border-border-subtle rounded-xl p-3 shadow-card flex flex-col gap-2">
        <p className="text-[10px] uppercase tracking-widest text-txt-muted font-bold">Graph Controls</p>

        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search nodes…"
          className="w-full bg-elevated border border-border-subtle rounded-lg px-3 py-1.5 text-sm text-txt placeholder:text-txt-muted focus:border-accent focus:outline-none"
        />

        <select
          value={categoryFilter}
          onChange={e => setCategoryFilter(e.target.value)}
          className="w-full bg-elevated border border-border-subtle rounded-lg px-3 py-1.5 text-sm text-txt focus:border-accent focus:outline-none"
        >
          <option value="">All types</option>
          {categories.map(c => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>

        <button
          onClick={resetZoom}
          className="bg-elevated border border-border-subtle rounded-lg px-3 py-1.5 text-sm text-txt-dim hover:text-txt hover:bg-hover transition text-left"
        >
          Reset zoom
        </button>

        <div className="pt-1 border-t border-border-subtle text-xs text-txt-muted">
          {allNotes.length} notes · {filteredCount} connections
        </div>
      </div>

      {/* Graph canvas */}
      <div ref={containerRef} className="w-full h-full">
        <svg ref={svgRef} className="w-full h-full" />
      </div>

      {/* Hover tooltip */}
      {tooltip && (
        <div
          className="fixed z-20 pointer-events-none bg-card border border-border-subtle rounded-lg px-3 py-2 text-sm shadow-lg max-w-[200px]"
          style={{ left: tooltip.x + 14, top: tooltip.y - 12 }}
        >
          {tooltip.note ? (
            <>
              <p className="font-semibold text-txt truncate">{tooltip.note.title}</p>
              {tooltip.note.tags?.length > 0 && (
                <p className="text-txt-muted text-xs mt-0.5 truncate">{tooltip.note.tags.join(', ')}</p>
              )}
              <p className="text-txt-muted text-xs mt-1 opacity-60">Click to open</p>
            </>
          ) : (
            <p className="text-txt">{tooltip.text}</p>
          )}
        </div>
      )}
    </div>
  );
}
