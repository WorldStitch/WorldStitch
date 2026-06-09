import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import clsx from "clsx";
import { Map, Plus, Trash2, X, AlertCircle, Layers } from "lucide-react";
import { maps } from "../api";
import { useVault } from "@/context/VaultContext";
import { SkeletonListItem } from "@/components/Skeleton";

const MAP_TYPES = ["region", "dungeon", "city", "world"];

const mapSchema = z.object({
  name: z.string().min(1, "Name is required"),
  map_type: z.string().default("region"),
  description: z.string().default(""),
  image_url: z.string().default(""),
  map_url: z.string().default(""),
  tags: z.string().default(""),
});

const markerSchema = z.object({
  label: z.string().min(1, "Label is required"),
  x: z.coerce.number(),
  y: z.coerce.number(),
});

function TypeBadge({ type }) {
  const colors = {
    region: "bg-green-900/40 text-green-300",
    dungeon: "bg-red-900/40 text-red-300",
    city: "bg-blue-900/40 text-blue-300",
    world: "bg-purple-900/40 text-purple-300",
  };
  return (
    <span className={clsx("text-xs px-2 py-0.5 rounded-full font-medium", colors[type] ?? "bg-surface text-txt-muted")}>
      {type}
    </span>
  );
}

export default function Maps() {
  const qc = useQueryClient();
  const { activeVaultId } = useVault();
  const navigate = useNavigate();
  const [selectedId, setSelectedId] = useState(null);
  const [filterType, setFilterType] = useState(null);
  const [search, setSearch] = useState("");
  const [showMarkerForm, setShowMarkerForm] = useState(false);
  const [markers, setMarkers] = useState([]);

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
    formState: { errors, isDirty },
  } = useForm({ resolver: zodResolver(mapSchema) });

  const {
    register: regMarker,
    handleSubmit: handleMarkerSubmit,
    reset: resetMarker,
    formState: { errors: markerErrors },
  } = useForm({ resolver: zodResolver(markerSchema) });

  // ── List query ──────────────────────────────────────────────────────────────
  const { data: listData, isLoading, isError, refetch } = useQuery({
    queryKey: ["maps", activeVaultId, filterType],
    queryFn: () => maps.list(activeVaultId, filterType),
    enabled: !!activeVaultId,
  });

  useEffect(() => {
    if (isError) toast.error("Failed to load maps");
  }, [isError]);

  const allMaps = listData?.items ?? [];
  const filtered = search
    ? allMaps.filter((m) => m.name.toLowerCase().includes(search.toLowerCase()))
    : allMaps;

  // ── Detail query ────────────────────────────────────────────────────────────
  const { data: detail } = useQuery({
    queryKey: ["maps", selectedId],
    queryFn: () => maps.get(selectedId),
    enabled: !!selectedId,
  });

  // Sync form + markers when detail loads
  const handleSelect = (m) => {
    setSelectedId(m.id);
    setShowMarkerForm(false);
  };

  // When detail arrives, populate form
  const populateForm = (d) => {
    reset({
      name: d.name,
      map_type: d.map_type ?? "region",
      description: d.description ?? "",
      image_url: d.image_url ?? "",
      map_url: d.map_url ?? "",
      tags: Array.isArray(d.tags) ? d.tags.join(", ") : (d.metadata?.tags ?? []).join(", "),
    });
    setMarkers(d.markers ?? d.metadata?.markers ?? []);
  };

  if (detail && detail.id === selectedId) {
    const formName = watch("name");
    if (formName === undefined) {
      populateForm(detail);
    }
  }

  // ── Mutations ───────────────────────────────────────────────────────────────
  const createMut = useMutation({
    mutationFn: (data) => maps.create(data),
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["maps"] });
      setSelectedId(created.id);
      toast.success("Map created");
    },
    onError: (e) => toast.error(e.message),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }) => maps.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["maps"] });
      toast.success("Map saved");
    },
    onError: (e) => toast.error(e.message),
  });

  const deleteMut = useMutation({
    mutationFn: (id) => maps.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["maps"] });
      setSelectedId(null);
      reset();
      setMarkers([]);
      toast.success("Map deleted");
    },
    onError: (e) => toast.error(e.message),
  });

  // ── Form submit ─────────────────────────────────────────────────────────────
  const onSubmit = (values) => {
    const payload = {
      name: values.name,
      map_type: values.map_type,
      description: values.description,
      image_url: values.image_url,
      map_url: values.map_url,
      tags: values.tags,
      markers: markers.map((mk, i) => ({ id: mk.id || String(i), ...mk })),
    };

      if (selectedId) {
        updateMut.mutate({ id: selectedId, data: payload });
      } else {
        createMut.mutate({ ...payload, vault_id: activeVaultId });
      }
    };

  // ── New map ─────────────────────────────────────────────────────────────────
  const handleNew = () => {
    setSelectedId(null);
    setMarkers([]);
    setShowMarkerForm(false);
    reset({ name: "", map_type: "region", description: "", image_url: "", map_url: "", tags: "" });
  };

  // ── Add marker ──────────────────────────────────────────────────────────────
  const onAddMarker = (vals) => {
    const newMarker = {
      id: crypto.randomUUID(),
      label: vals.label,
      x: vals.x,
      y: vals.y,
      note_id: "",
    };
    setMarkers((prev) => [...prev, newMarker]);
    resetMarker();
    setShowMarkerForm(false);
  };

  const removeMarker = (id) => {
    setMarkers((prev) => prev.filter((mk) => mk.id !== id));
  };

  // ── Render ──────────────────────────────────────────────────────────────────
  if (!activeVaultId) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3 text-txt-muted">
        <Layers size={48} className="opacity-20" />
        <p className="text-sm font-medium">No vault selected</p>
        <p className="text-xs text-center max-w-xs">Select or create a vault to manage maps.</p>
        <button
          onClick={() => navigate('/vaults')}
          className="mt-1 text-xs bg-accent text-white px-4 py-2 rounded-lg hover:bg-accent/90 transition-colors"
        >
          Go to Vaults
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-full">
      {/* Left panel */}
      <div className="w-72 flex-shrink-0 border-r border-border-subtle flex flex-col h-full">
        {/* Header */}
        <div className="px-4 py-4 border-b border-border-subtle flex items-center justify-between">
          <h2 className="font-semibold text-txt flex items-center gap-2">
            <Map size={18} /> Maps
          </h2>
          <button
            onClick={handleNew}
            className="flex items-center gap-1 text-xs bg-accent text-white px-2 py-1 rounded-lg hover:bg-accent/80 transition-colors"
          >
            <Plus size={14} /> New
          </button>
        </div>

        {/* Search */}
        <div className="px-3 py-2 border-b border-border-subtle">
          <input
            type="text"
            placeholder="Search maps..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-base border border-border-subtle rounded-lg px-3 py-1.5 text-sm text-txt placeholder:text-txt-muted focus:outline-none focus:ring-1 focus:ring-accent"
          />
        </div>

        {/* Type filter tabs */}
        <div className="flex flex-wrap gap-1 px-3 py-2 border-b border-border-subtle">
          <button
            onClick={() => setFilterType(null)}
            className={clsx(
              "text-xs px-2 py-0.5 rounded-full font-medium transition-colors",
              filterType === null ? "bg-accent text-white" : "bg-surface text-txt-muted hover:bg-hover"
            )}
          >
            All
          </button>
          {MAP_TYPES.map((t) => (
            <button
              key={t}
              onClick={() => setFilterType(t === filterType ? null : t)}
              className={clsx(
                "text-xs px-2 py-0.5 rounded-full font-medium transition-colors capitalize",
                filterType === t ? "bg-accent text-white" : "bg-surface text-txt-muted hover:bg-hover"
              )}
            >
              {t}
            </button>
          ))}
        </div>

        {/* Map list */}
        <div className="flex-1 overflow-y-auto py-2">
          {isLoading ? (
            <div className="space-y-2 px-3 pt-1">
              {Array.from({ length: 4 }).map((_, i) => <SkeletonListItem key={i} />)}
            </div>
          ) : isError ? (
            <div className="flex flex-col items-center gap-2 py-6 px-4 text-center">
              <AlertCircle size={20} className="text-red-400 opacity-70" />
              <p className="text-txt-muted text-xs">Failed to load maps.</p>
              <button onClick={() => refetch()} className="text-xs text-accent hover:underline">
                Retry
              </button>
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-6 px-4 text-center">
              <Map size={28} className="opacity-20" />
              <p className="text-txt-muted text-sm">
                {search ? 'No maps match your search.' : 'No maps yet. Click New to add one.'}
              </p>
            </div>
          ) : null}
          {!isLoading && !isError && filtered.map((m) => (
            <button
              key={m.id}
              onClick={() => handleSelect(m)}
              className={clsx(
                "w-full text-left px-4 py-3 border-b border-border-subtle transition-colors",
                selectedId === m.id ? "bg-accent-soft" : "hover:bg-hover"
              )}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium text-txt truncate">{m.name}</span>
                <TypeBadge type={m.map_type} />
              </div>
              {m.description && (
                <p className="text-xs text-txt-muted truncate">{m.description}</p>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Right panel */}
      <div className="flex-1 overflow-y-auto p-6">
        {!selectedId && !watch("name") ? (
          <div className="flex flex-col items-center justify-center h-full text-center text-txt-muted">
            <Map size={48} className="mb-4 opacity-30" />
            <p className="text-sm">Select a map or create a new one.</p>
          </div>
        ) : (
          <form onSubmit={handleSubmit(onSubmit)} className="max-w-2xl">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-semibold text-txt">
                {selectedId ? "Edit Map" : "New Map"}
              </h3>
              <div className="flex gap-2">
                {selectedId && (
                  <button
                    type="button"
                    onClick={() => deleteMut.mutate(selectedId)}
                    disabled={deleteMut.isPending}
                    className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border border-red-700 text-red-400 hover:bg-red-900/20 transition-colors"
                  >
                    <Trash2 size={14} /> Delete
                  </button>
                )}
                <button
                  type="submit"
                  disabled={createMut.isPending || updateMut.isPending}
                  className="flex items-center gap-1.5 text-sm bg-accent text-white px-4 py-1.5 rounded-lg hover:bg-accent/80 transition-colors disabled:opacity-50"
                >
                  {createMut.isPending || updateMut.isPending ? "Saving…" : "Save"}
                </button>
              </div>
            </div>

            {/* Name */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-txt mb-1">Name *</label>
              <input
                {...register("name")}
                className="w-full bg-base border border-border-subtle rounded-lg px-3 py-2 text-sm text-txt focus:outline-none focus:ring-1 focus:ring-accent"
              />
              {errors.name && (
                <p className="text-red-400 text-xs mt-1">{errors.name.message}</p>
              )}
            </div>

            {/* Type */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-txt mb-1">Type</label>
              <select
                {...register("map_type")}
                className="w-full bg-base border border-border-subtle rounded-lg px-3 py-2 text-sm text-txt focus:outline-none focus:ring-1 focus:ring-accent"
              >
                {MAP_TYPES.map((t) => (
                  <option key={t} value={t} className="capitalize">
                    {t.charAt(0).toUpperCase() + t.slice(1)}
                  </option>
                ))}
              </select>
            </div>

            {/* Description */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-txt mb-1">Description</label>
              <textarea
                {...register("description")}
                rows={4}
                className="w-full bg-base border border-border-subtle rounded-lg px-3 py-2 text-sm text-txt focus:outline-none focus:ring-1 focus:ring-accent resize-y"
              />
            </div>

            {/* Image URL */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-txt mb-1">Image URL</label>
              <input
                {...register("image_url")}
                placeholder="https://… thumbnail or preview image"
                className="w-full bg-base border border-border-subtle rounded-lg px-3 py-2 text-sm text-txt placeholder:text-txt-muted focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>

            {/* Map URL */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-txt mb-1">Map URL</label>
              <input
                {...register("map_url")}
                placeholder="https://… full-resolution map file"
                className="w-full bg-base border border-border-subtle rounded-lg px-3 py-2 text-sm text-txt placeholder:text-txt-muted focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>

            {/* Tags */}
            <div className="mb-6">
              <label className="block text-sm font-medium text-txt mb-1">Tags</label>
              <input
                {...register("tags")}
                placeholder="e.g. wilderness, explored, hostile"
                className="w-full bg-base border border-border-subtle rounded-lg px-3 py-2 text-sm text-txt placeholder:text-txt-muted focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>

            {/* Markers section */}
            <div className="border-t border-border-subtle pt-5">
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-sm font-semibold text-txt">Markers</h4>
                <button
                  type="button"
                  onClick={() => setShowMarkerForm((v) => !v)}
                  className="flex items-center gap-1 text-xs bg-surface border border-border-subtle px-2 py-1 rounded-lg text-txt-dim hover:bg-hover transition-colors"
                >
                  <Plus size={13} /> Add Marker
                </button>
              </div>

              {/* Inline add-marker form */}
              {showMarkerForm && (
                <div className="mb-3 p-3 bg-surface border border-border-subtle rounded-xl">
                  <div className="flex gap-2 items-start">
                    <div className="flex-1">
                      <input
                        {...regMarker("label")}
                        placeholder="Label"
                        className="w-full bg-base border border-border-subtle rounded-lg px-2 py-1.5 text-sm text-txt placeholder:text-txt-muted focus:outline-none focus:ring-1 focus:ring-accent mb-1"
                      />
                      {markerErrors.label && (
                        <p className="text-red-400 text-xs">{markerErrors.label.message}</p>
                      )}
                    </div>
                    <div className="w-20">
                      <input
                        {...regMarker("x")}
                        placeholder="X"
                        type="number"
                        className="w-full bg-base border border-border-subtle rounded-lg px-2 py-1.5 text-sm text-txt placeholder:text-txt-muted focus:outline-none focus:ring-1 focus:ring-accent"
                      />
                    </div>
                    <div className="w-20">
                      <input
                        {...regMarker("y")}
                        placeholder="Y"
                        type="number"
                        className="w-full bg-base border border-border-subtle rounded-lg px-2 py-1.5 text-sm text-txt placeholder:text-txt-muted focus:outline-none focus:ring-1 focus:ring-accent"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={handleMarkerSubmit(onAddMarker)}
                      className="text-xs bg-accent text-white px-3 py-1.5 rounded-lg hover:bg-accent/80 transition-colors"
                    >
                      Add
                    </button>
                    <button
                      type="button"
                      onClick={() => { setShowMarkerForm(false); resetMarker(); }}
                      className="text-txt-muted hover:text-txt transition-colors"
                    >
                      <X size={16} />
                    </button>
                  </div>
                </div>
              )}

              {/* Markers list */}
              {markers.length === 0 ? (
                <p className="text-xs text-txt-muted py-2">No markers yet.</p>
              ) : (
                <div className="space-y-1">
                  {markers.map((mk) => (
                    <div
                      key={mk.id}
                      className="flex items-center justify-between px-3 py-2 bg-surface rounded-lg border border-border-subtle"
                    >
                      <span className="text-sm font-medium text-txt">{mk.label}</span>
                      <div className="flex items-center gap-3">
                        <span className="text-xs text-txt-muted">
                          ({mk.x}, {mk.y})
                        </span>
                        <button
                          type="button"
                          onClick={() => removeMarker(mk.id)}
                          className="text-txt-muted hover:text-red-400 transition-colors"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
