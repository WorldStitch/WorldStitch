import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { relationships as relApi } from "@/api";

// Groups types by category for the <select> optgroups.
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

	const { data: types = [] } = useQuery({
		queryKey: ["relationship-types"],
		queryFn: relApi.getTypes,
		staleTime: Infinity,
	});

	// When type changes, auto-set the default direction from the registry.
	useEffect(() => {
		if (!isEdit && relType) {
			const entry = types.find((t) => t.type === relType);
			if (entry) setDirection(entry.default_direction ?? "bidirectional");
		}
	}, [relType, isEdit, types]);

	const grouped = groupByCategory(types);

	const handleSubmit = async (e) => {
		e.preventDefault();
		if (!targetId.trim()) {
			setError("Target entity is required.");
			return;
		}
		if (!relType) {
			setError("Relationship type is required.");
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

	const selectedEntry = types.find((t) => t.type === relType);
	const inverseHint = selectedEntry?.inverse
		? `inverse: "${selectedEntry.inverse}"`
		: null;

	return (
		<form onSubmit={handleSubmit} className="space-y-3 pt-2">
			{/* Source — read-only */}
			<div>
				<p className="text-[10px] uppercase tracking-widest text-txt-muted font-bold mb-1">
					Source
				</p>
				<div className="text-xs text-txt bg-elevated rounded-lg px-2 py-1.5 border border-txt-muted/10 font-mono truncate">
					{entityId}
				</div>
			</div>

			{/* Target */}
			{!isEdit && (
				<div>
					<p className="text-[10px] uppercase tracking-widest text-txt-muted font-bold mb-1">
						Target entity
					</p>
					{allNotes && allNotes.length > 0 ? (
						<>
							<input
								list="relationship-target-notes"
								value={targetInput}
								onChange={(e) => {
									const val = e.target.value;
									setTargetInput(val);
									const match = allNotes.find((n) => n.title === val);
									if (match) {
										setTargetId(match.id);
									} else {
										setTargetId(val);
									}
								}}
								placeholder="Search note by title…"
								className="w-full bg-elevated rounded-lg px-2 py-1.5 text-xs text-txt border border-transparent focus:border-accent focus:outline-none"
							/>
							<datalist id="relationship-target-notes">
								{allNotes
									.filter((n) => n.id !== entityId)
									.map((n) => (
										<option key={n.id} value={n.title} />
									))}
							</datalist>
							<p className="text-[10px] text-txt-muted mt-0.5 px-0.5">
								Type or pick a note title — the UUID is stored automatically.
							</p>
						</>
					) : (
						<input
							value={targetId}
							onChange={(e) => setTargetId(e.target.value)}
							placeholder="Entity ID or name…"
							className="w-full bg-elevated rounded-lg px-2 py-1.5 text-xs text-txt border border-transparent focus:border-accent focus:outline-none"
						/>
					)}
				</div>
			)}

			{/* Type grouped select */}
			<div>
				<p className="text-[10px] uppercase tracking-widest text-txt-muted font-bold mb-1">
					Type
				</p>
				<select
					value={relType}
					onChange={(e) => setRelType(e.target.value)}
					className="w-full bg-elevated rounded-lg px-2 py-1.5 text-xs text-txt border border-transparent focus:border-accent focus:outline-none"
				>
					<option value="">Select type…</option>
					{Object.entries(grouped).map(([cat, entries]) => (
						<optgroup key={cat} label={cat}>
							{entries.map((t) => (
								<option key={t.type} value={t.type}>
									{t.type}
									{t.inverse ? ` (${t.inverse})` : ""}
								</option>
							))}
						</optgroup>
					))}
				</select>
				{inverseHint && (
					<p className="text-[10px] text-txt-muted mt-0.5 px-0.5">
						{inverseHint}
					</p>
				)}
			</div>

			{/* Direction */}
			<div>
				<p className="text-[10px] uppercase tracking-widest text-txt-muted font-bold mb-1">
					Direction
				</p>
				<div className="flex gap-4">
					{["bidirectional", "unidirectional"].map((d) => (
						<label
							key={d}
							className="flex items-center gap-1.5 text-xs text-txt cursor-pointer"
						>
							<input
								type="radio"
								name="direction"
								value={d}
								checked={direction === d}
								onChange={() => setDirection(d)}
								className="accent-[var(--color-accent)]"
							/>
							{d}
						</label>
					))}
				</div>
			</div>

			{/* Label override */}
			<div>
				<p className="text-[10px] uppercase tracking-widest text-txt-muted font-bold mb-1">
					Label{" "}
					<span className="normal-case font-normal">(optional override)</span>
				</p>
				<input
					value={label}
					onChange={(e) => setLabel(e.target.value)}
					placeholder="Custom display label…"
					className="w-full bg-elevated rounded-lg px-2 py-1.5 text-xs text-txt border border-transparent focus: