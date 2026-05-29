import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { relationships as relApi } from "@/api";

function groupByCategory(types) {
	const map = {};
	for (const t of types) {
		if (!map[t.category]) map[t.category] = [];
		map[t.category].push(t);
	}
	return map;
}

export default function RelationshipForm({
	entityId,
	vaultId,
	existing,
	onSave,
	onCancel,
	allNotes,
}) {
	const isEdit = !!existing;

	const [targetId, setTargetId] = useState(existing?.target_id ?? "");
	const [targetInput, setTargetInput] = useState(() => {
		if (existing?.target_id && allNotes) {
			const found = allNotes.find((n) => n.id === existing.target_id);
			return found ? found.title : existing.target_id;
		}
		return "";
	});
	const [relType, setRelType] = useState(existing?.relationship_type ?? "");
	const [direction, setDirection] = useState(
		existing?.direction ?? "bidirectional",
	);
	const [label, setLabel] = useState(existing?.label ?? "");
	const [weight, setWeight] = useState(existing?.weight ?? 1.0);
	const [error, setError] = useState("");
	const [saving, setSaving] = useState(false);
	const [activeCategory, setActiveCategory] = useState(null);

	const { data: types = [] } = useQuery({
		queryKey: ["relationship-types"],
		queryFn: relApi.getTypes,
		staleTime: Infinity,
	});

	// Set initial category once types load.
	useEffect(() => {
		if (types.length > 0 && !activeCategory) {
			const grouped = groupByCategory(types);
			setActiveCategory(Object.keys(grouped)[0]);
		}
	}, [types, activeCategory]);

	// Auto-set direction from type registry.
	useEffect(() => {
		if (!isEdit && relType) {
			const entry = types.find((t) => t.type === relType);
			if (entry) setDirection(entry.default_direction ?? "bidirectional");
		}
	}, [relType, isEdit, types]);

	const grouped = groupByCategory(types);
	const categories = Object.keys(grouped);
	const typesInCategory = activeCategory ? (grouped[activeCategory] || []) : [];

	const sourceNote = allNotes?.find((n) => n.id === entityId);
	const sourceTitle = sourceNote?.title || entityId;

	const handleSubmit = async (e) => {
		e.preventDefault();
		if (!targetId.trim()) {
			setError("Please select a note to connect to.");
			return;
		}
		if (!relType) {
			setError("Please select a relationship type.");
			return;
		}
		setError("");
		setSaving(true);
		try {
			if (isEdit) {
				await relApi.update(existing.id, {
					relationship_type: relType,
					direction,
					label: label.trim() || null,
					weight,
				});
			} else {
				await relApi.create({
					source_id: entityId,
					target_id: targetId.trim(),
					relationship_type: relType,
					direction,
					label: label.trim() || null,
					weight,
					vault_id: vaultId,
				});
			}
			onSave?.();
		} catch (err) {
			setError(err.message || "Failed to save relationship.");
		} finally {
			setSaving(false);
		}
	};

	return (
		<form onSubmit={handleSubmit} className="space-y-3 pt-2">
			{/* Source pill */}
			<div className="text-xs text-txt-muted">
				Connecting from:{" "}
				<span className="text-txt font-medium">{sourceTitle}</span>
			</div>

			{/* Connect to */}
			{!isEdit && (
				<div>
					<label className="text-[10px] uppercase tracking-widest text-txt-muted font-bold block mb-1">
						Connect to
					</label>
					{allNotes && allNotes.length > 0 ? (
						<>
							<input
								list="relationship-target-notes"
								value={targetInput}
								onChange={(e) => {
									const val = e.target.value;
									setTargetInput(val);
									const match = allNotes.find((n) => n.title === val);
									setTargetId(match ? match.id : val);
								}}
								placeholder="🔍 Search notes…"
								className="w-full bg-elevated rounded-lg px-2 py-1.5 text-xs text-txt border border-transparent focus:border-accent focus:outline-none"
							/>
							<datalist id="relationship-target-notes">
								{allNotes
									.filter((n) => n.id !== entityId)
									.map((n) => (
										<option key={n.id} value={n.title} />
									))}
							</datalist>
						</>
					) : (
						<input
							value={targetId}
							onChange={(e) => setTargetId(e.target.value)}
							placeholder="🔍 Search notes…"
							className="w-full bg-elevated rounded-lg px-2 py-1.5 text-xs text-txt border border-transparent focus:border-accent focus:outline-none"
						/>
					)}
				</div>
			)}

			{/* Relationship type — category tabs + pills */}
			<div>
				<label className="text-[10px] uppercase tracking-widest text-txt-muted font-bold block mb-1">
					Relationship type
				</label>
				{categories.length > 0 ? (
					<>
						{/* Category tabs */}
						<div className="flex flex-wrap gap-1 mb-2">
							{categories.map((cat) => (
								<button
									key={cat}
									type="button"
									onClick={() => setActiveCategory(cat)}
									className={`text-[10px] px-2 py-0.5 rounded-full border transition ${
										activeCategory === cat
											? "bg-accent text-white border-accent"
											: "border-txt-muted/20 text-txt-muted hover:border-accent/50"
									}`}
								>
									{cat}
								</button>
							))}
						</div>
						{/* Type pills */}
						<div className="flex flex-wrap gap-1">
							{typesInCategory.map((t) => (
								<button
									key={t.type}
									type="button"
									onClick={() => setRelType(t.type)}
									className={`text-xs px-2.5 py-1 rounded-lg border transition ${
										relType === t.type
											? "bg-accent text-white border-accent"
											: "border-txt-muted/20 text-txt hover:border-accent/50 hover:bg-accent/5"
									}`}
								>
									{t.type}
								</button>
							))}
						</div>
					</>
				) : (
					<p className="text-xs text-txt-muted">Loading types…</p>
				)}
			</div>

			{/* Advanced options — collapsed by default */}
			<details className="mb-1">
				<summary className="text-[10px] text-txt-muted cursor-pointer hover:text-txt select-none">
					Advanced options ▾
				</summary>
				<div className="mt-2 space-y-2 pl-2 border-l border-txt-muted/10">
					{/* Direction */}
					<div>
						<p className="text-[10px] uppercase tracking-widest text-txt-muted font-bold mb-1">
							Direction
						</p>
						<div className="flex gap-2">
							<button
								type="button"
								onClick={() => setDirection("bidirectional")}
								className={`text-xs px-2.5 py-1 rounded-lg border transition ${
									direction === "bidirectional"
										? "bg-accent text-white border-accent"
										: "border-txt-muted/20 text-txt hover:border-accent/50"
								}`}
							>
								↔ Both ways
							</button>
							<button
								type="button"
								onClick={() => setDirection("unidirectional")}
								className={`text-xs px-2.5 py-1 rounded-lg border transition ${
									direction === "unidirectional"
										? "bg-accent text-white border-accent"
										: "border-txt-muted/20 text-txt hover:border-accent/50"
								}`}
							>
								→ One way
							</button>
						</div>
					</div>

					{/* Label */}
					<div>
						<p className="text-[10px] uppercase tracking-widest text-txt-muted font-bold mb-1">
							Label{" "}
							<span className="normal-case font-normal">(optional)</span>
						</p>
						<input
							value={label}
							onChange={(e) => setLabel(e.target.value)}
							placeholder="Custom display label…"
							className="w-full bg-elevated rounded-lg px-2 py-1.5 text-xs text-txt border border-transparent focus:border-accent focus:outline-none"
						/>
					</div>

					{/* Weight */}
					<div>
						<p className="text-[10px] uppercase tracking-widest text-txt-muted font-bold mb-1">
							Weight{" "}
							<span className="normal-case font-normal text-txt-muted">
								{weight.toFixed(2)}
							</span>
						</p>
						<input
							type="range"
							min="0"
							max="1"
							step="0.05"
							value={weight}
							onChange={(e) => setWeight(parseFloat(e.target.value))}
							className="w-full accent-[var(--color-accent)]"
						/>
					</div>
				</div>
			</details>

			{/* Error */}
			{error && (
				<p className="text-xs text-danger bg-danger/10 rounded-lg px-2 py-1.5">
					{error}
				</p>
			)}

			{/* Buttons */}
			<div className="flex gap-2 pt-1">
				<button
					type="submit"
					disabled={saving}
					className="flex-1 bg-accent text-white text-xs font-semibold py-1.5 rounded-lg hover:bg-accent/90 transition disabled:opacity-50"
				>
					{saving ? "Saving…" : isEdit ? "Save changes" : "Add connection"}
				</button>
				<button
					type="button"
					onClick={onCancel}
					className="text-xs text-txt-muted hover:text-txt px-3 py-1.5 rounded-lg hover:bg-hover transition"
				>
					Cancel
				</button>
			</div>
		</form>
	);
}
