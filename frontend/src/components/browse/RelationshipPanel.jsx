import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Network, Plus, Pencil, Trash2 } from "lucide-react";
import { relationships as relApi } from "@/api";
import { SkeletonLine } from "@/components/Skeleton";
import RelationshipForm from "./RelationshipForm";

function WeightDot({ weight }) {
	const opacity = Math.max(0.2, weight);
	return (
		<span
			className="inline-block w-1.5 h-1.5 rounded-full bg-accent flex-shrink-0"
			style={{ opacity }}
			title={`Weight: ${weight.toFixed(2)}`}
		/>
	);
}

function RelRow({ rel, entityId, allNotes, onNavigate, onEdit, onDelete }) {
	const isSource = rel.source_id === entityId;
	const displayLabel = rel.label || rel.relationship_type;
	const otherId = isSource ? rel.target_id : rel.source_id;
	const otherNote = allNotes.find((n) => n.id === otherId);
	const otherTitle = otherNote?.title || otherId;

	return (
		<div className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-hover transition group">
			<div className="flex-1 min-w-0 flex items-center gap-1.5 flex-wrap">
				<button
					onClick={() => onNavigate?.(otherId)}
					className="text-xs text-txt hover:text-accent hover:underline truncate transition"
					title={otherTitle}
				>
					{otherTitle}
				</button>
				<span className="text-[10px] text-txt-muted">→</span>
				<span className="inline-flex items-center gap-1 text-[10px] font-medium text-accent bg-accent/10 px-1.5 py-0.5 rounded-full flex-shrink-0">
					{displayLabel}
					<WeightDot weight={rel.weight} />
				</span>
			</div>
			<div className="hidden group-hover:flex items-center gap-1 flex-shrink-0">
				<button
					type="button"
					onClick={() => onEdit(rel)}
					className="text-txt-muted hover:text-accent transition p-0.5 rounded hover:bg-accent/10"
					title="Edit"
				>
					<Pencil size={10} />
				</button>
				<button
					type="button"
					onClick={() => onDelete(rel)}
					className="text-txt-muted hover:text-danger transition p-0.5 rounded hover:bg-danger/10"
					title="Delete"
				>
					<Trash2 size={10} />
				</button>
			</div>
		</div>
	);
}

export default function RelationshipPanel({ entityId, vaultId, allNotes = [], onNavigate, headless = false }) {
	const navigate = useNavigate();
	const queryClient = useQueryClient();
	const [showForm, setShowForm] = useState(false);
	const [editing, setEditing] = useState(null);
	const [deleteError, setDeleteError] = useState("");

	const {
		data = [],
		isLoading,
		error,
	} = useQuery({
		queryKey: ["relationships", entityId, vaultId],
		queryFn: () => relApi.list(vaultId, entityId),
		enabled: !!entityId && !!vaultId,
		staleTime: 30_000,
	});

	const invalidate = () =>
		queryClient.invalidateQueries({
			queryKey: ["relationships", entityId, vaultId],
		});

	const handleDelete = async (rel) => {
		if (!confirm(`Delete this "${rel.relationship_type}" relationship?`))
			return;
		setDeleteError("");
		try {
			await relApi.delete(rel.id);
			invalidate();
		} catch (err) {
			setDeleteError(err.message || "Delete failed.");
		}
	};

	const handleSave = () => {
		setShowForm(false);
		setEditing(null);
		invalidate();
	};

	const handleEdit = (rel) => {
		setEditing(rel);
		setShowForm(false);
	};

	const byCategory = {};
	for (const rel of data) {
		const cat = rel.relationship_type || rel.category || "Other";
		if (!byCategory[cat]) byCategory[cat] = [];
		byCategory[cat].push(rel);
	}

	const total = data.length;

	return (
		<div>
			{/* Action bar — always shown, replaces the old header when headless */}
			<div className="flex items-center gap-1 mb-2 justify-end">
				<button
					onClick={() => navigate(`/graph?note=${entityId}`)}
					className="text-txt-muted hover:text-accent transition p-1 rounded"
					title="View in Graph"
				>
					<Network size={13} />
				</button>
				{!showForm && !editing && (
					<button
						type="button"
						onClick={() => setShowForm(true)}
						className="flex items-center gap-1 text-accent text-xs font-medium px-2 py-1 rounded-lg hover:bg-accent/10 transition"
						title="Add connection"
					>
						<Plus size={12} />
						Add
					</button>
				)}
			</div>

			{/* Inline add form */}
			{showForm && (
				<div className="mb-3 border border-txt-muted/10 rounded-xl p-3 bg-elevated/40">
					<RelationshipForm
						entityId={entityId}
						vaultId={vaultId}
						allNotes={allNotes}
						onSave={handleSave}
						onCancel={() => setShowForm(false)}
					/>
				</div>
			)}

			{/* Inline edit form */}
			{editing && (
				<div className="mb-3 border border-txt-muted/10 rounded-xl p-3 bg-elevated/40">
					<RelationshipForm
						entityId={entityId}
						vaultId={vaultId}
						allNotes={allNotes}
						existing={editing}
						onSave={handleSave}
						onCancel={() => setEditing(null)}
					/>
				</div>
			)}

			{deleteError && (
				<p className="text-xs text-danger bg-danger/10 rounded-lg px-2 py-1.5 mb-2">
					{deleteError}
				</p>
			)}

			{isLoading ? (
				<div className="space-y-1.5">
					<SkeletonLine width="w-3/4" />
					<SkeletonLine width="w-1/2" />
					<SkeletonLine width="w-2/3" />
				</div>
			) : error ? (
				<p className="text-xs text-danger">Failed to load connections.</p>
			) : total === 0 && !showForm ? (
				<p className="text-xs text-txt-muted/70 italic">
					No connections yet — use the Add button to link this entry to others in your vault.
				</p>
			) : total > 0 ? (
				<div className="space-y-2">
					{Object.entries(byCategory).map(([cat, rels]) => (
						<div key={cat}>
							<p className="text-[10px] uppercase tracking-widest text-txt-muted/50 font-semibold px-1 mb-0.5">
								{cat}
							</p>
							<div className="space-y-0.5">
								{rels.map((rel) => (
									<RelRow
										key={rel.id}
										rel={rel}
										entityId={entityId}
										allNotes={allNotes}
										onNavigate={onNavigate}
										onEdit={handleEdit}
										onDelete={handleDelete}
									/>
								))}
							</div>
						</div>
					))}
				</div>
			) : null}
		</div>
	);
}
