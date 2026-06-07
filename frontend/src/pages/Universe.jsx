import { useState, useEffect } from 'react';
import { toast } from 'sonner';
import SectionHeader from '@/components/SectionHeader';
import Card from '@/components/Card';
import Button from '@/components/Button';
import Input, { TextArea } from '@/components/Input';
import { notes } from '@/api';

// ════════════════════════════════════════════════════════════════════════════
// Universe Timeline — persisted via Notes API with meta.type = timeline_event
// ════════════════════════════════════════════════════════════════════════════

const TIMELINE_TAG = 'timeline-event';

export default function Universe() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [showForm, setShowForm] = useState(false);

  // Form state
  const [formTitle, setFormTitle] = useState('');
  const [formDate, setFormDate] = useState('');
  const [formDescription, setFormDescription] = useState('');
  const [formCategory, setFormCategory] = useState('event');
  const [editingId, setEditingId] = useState(null);

  // ── Load timeline events ─────────────────────────────────────────────
  const loadEvents = async () => {
    try {
      const allNotes = await notes.list('', TIMELINE_TAG);
      const mapped = allNotes.map((n) => ({
        id: n.id,
        title: n.title,
        // Prefer meta fields; fall back to legacy tag encoding for existing data
        date: n.meta?.event_date || n.tags?.find((t) => t.startsWith('date:'))?.slice(5) || '',
        category: n.meta?.category || n.tags?.find((t) => t.startsWith('cat:'))?.slice(4) || 'event',
        description: '',
        tags: n.tags || [],
        meta: n.meta || {},
        last_modified: n.last_modified,
      }));
      setEvents(mapped);
    } catch (err) {
      toast.error('Failed to load timeline');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadEvents(); }, []);

  // ── Select event (load full content) ─────────────────────────────────
  const handleSelectEvent = async (evt) => {
    setSelectedEvent(evt);
    try {
      const detail = await notes.get(evt.id);
      setSelectedEvent({
        ...evt,
        description: detail.content || '',
        meta: detail.meta || {},
        date: detail.meta?.event_date || evt.date,
        category: detail.meta?.category || evt.category,
      });
    } catch {
      // Event detail failed to load — selected event keeps its list-level data
    }
  };

  // ── Form helpers ─────────────────────────────────────────────────────
  const resetForm = () => {
    setFormTitle('');
    setFormDate('');
    setFormDescription('');
    setFormCategory('event');
    setEditingId(null);
    setShowForm(false);
  };

  const handleAddEvent = () => {
    resetForm();
    setShowForm(true);
  };

  const handleEditEvent = (evt) => {
    setEditingId(evt.id);
    setFormTitle(evt.title);
    setFormDate(evt.date || '');
    setFormCategory(evt.category || 'event');
    notes.get(evt.id).then((detail) => {
      setFormDescription(detail.content || '');
    }).catch(() => {
      // Could not pre-fill description — user can type manually
    });
    setShowForm(true);
  };

  // ── Save (create or update) ──────────────────────────────────────────
  const handleSave = async () => {
    if (!formTitle.trim()) return;

    const meta = {
      event_date: formDate || 'Unknown',
      category: formCategory,
    };

    try {
      if (editingId) {
        await notes.update(editingId, {
          title: formTitle,
          content: formDescription,
          tags: [TIMELINE_TAG],
          meta,
        });
        toast.success('Event updated');
      } else {
        await notes.create(formTitle, formDescription, null, [TIMELINE_TAG], meta);
        toast.success('Event created');
      }
      resetForm();
      await loadEvents();
    } catch (err) {
      toast.error('Failed to save: ' + err.message);
    }
  };

  // ── Delete ───────────────────────────────────────────────────────────
  const handleDeleteEvent = async (eventId) => {
    if (!confirm('Delete this timeline event?')) return;
    try {
      await notes.delete(eventId);
      if (selectedEvent?.id === eventId) setSelectedEvent(null);
      toast.success('Event deleted');
      await loadEvents();
    } catch (err) {
      toast.error('Failed to delete: ' + err.message);
    }
  };

  // ── Sort events by date field ────────────────────────────────────────
  const sortedEvents = [...events].sort((a, b) =>
    (a.date || '').localeCompare(b.date || '')
  );

  // ── Category colors ──────────────────────────────────────────────────
  const categoryColors = {
    event: 'bg-accent/20 text-accent',
    battle: 'bg-danger/20 text-danger',
    discovery: 'bg-green/20 text-green',
    political: 'bg-warning/20 text-warning',
    personal: 'bg-txt-dim/20 text-txt-dim',
  };

  // ════════════════════════════════════════════════════════════════════════
  // RENDER
  // ════════════════════════════════════════════════════════════════════════

  return (
    <div className="p-6 space-y-4 flex flex-col h-full">
      {/* Header */}
      <div className="flex justify-between items-start">
        <SectionHeader
          title="🌌 Universe Timeline"
          subtitle="Track events, story arcs, and history across your world."
        />
        <Button variant="primary" onClick={handleAddEvent}>+ Add Event</Button>
      </div>

      {/* Add/Edit Form */}
      {showForm && (
        <Card className="p-5 space-y-3">
          <h3 className="text-lg font-bold text-txt">
            {editingId ? 'Edit Event' : 'New Timeline Event'}
          </h3>
          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2">
              <Input
                label="Event Title"
                placeholder="The Fall of the Kingdom..."
                value={formTitle}
                onChange={(e) => setFormTitle(e.target.value)}
              />
            </div>
            <Input
              label="Date / Era"
              placeholder="Year 342, Third Age"
              value={formDate}
              onChange={(e) => setFormDate(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-txt-muted text-sm mb-1.5 font-medium">Category</label>
            <select
              value={formCategory}
              onChange={(e) => setFormCategory(e.target.value)}
              className="w-full bg-elevated rounded-xl px-4 py-3 text-txt border-2 border-transparent focus:border-accent focus:outline-none transition"
            >
              <option value="event">General Event</option>
              <option value="battle">Battle / Conflict</option>
              <option value="discovery">Discovery</option>
              <option value="political">Political / Diplomatic</option>
              <option value="personal">Personal / Character</option>
            </select>
          </div>

          <TextArea
            label="Description"
            placeholder="Describe what happened..."
            value={formDescription}
            onChange={(e) => setFormDescription(e.target.value)}
          />
          <div className="flex gap-3">
            <Button variant="primary" onClick={handleSave} disabled={!formTitle.trim()}>
              {editingId ? 'Update Event' : 'Create Event'}
            </Button>
            <Button variant="ghost" onClick={resetForm}>Cancel</Button>
          </div>
        </Card>
      )}

      {/* Main content */}
      <div className="flex gap-4 flex-1 overflow-hidden min-h-0">

        {/* Timeline list */}
        <Card className="flex-1 p-0 overflow-hidden flex flex-col">
          <div className="px-4 py-3 border-b border-txt-muted/10 flex justify-between items-center">
            <span className="text-sm font-bold text-txt">
              {sortedEvents.length} Event{sortedEvents.length !== 1 ? 's' : ''}
            </span>
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {loading ? (
              <p className="text-txt-muted text-sm p-4">Loading timeline...</p>
            ) : sortedEvents.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center space-y-3">
                <div className="text-5xl">📅</div>
                <p className="text-txt-muted">No timeline events yet.</p>
                <p className="text-txt-muted text-xs">Click + Add Event to start building your world's history.</p>
              </div>
            ) : (
              sortedEvents.map((event) => (
                <div
                  key={event.id}
                  onClick={() => handleSelectEvent(event)}
                  className={`flex gap-3 p-4 rounded-lg cursor-pointer transition group ${
                    selectedEvent?.id === event.id
                      ? 'bg-accent/10 border border-accent/30'
                      : 'bg-elevated hover:bg-hover'
                  }`}
                >
                  {/* Timeline dot + line */}
                  <div className="flex flex-col items-center flex-shrink-0">
                    <div className="w-3 h-3 rounded-full bg-accent mt-1" />
                    <div className="w-0.5 flex-1 bg-accent/20 mt-1" />
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex justify-between items-start gap-2">
                      <h3 className="font-bold text-txt truncate">{event.title}</h3>
                      <div className="flex gap-1 flex-shrink-0">
                        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                          categoryColors[event.category] || categoryColors.event
                        }`}>
                          {event.category}
                        </span>
                      </div>
                    </div>
                    <p className="text-txt-muted text-xs mt-0.5">{event.date || 'No date'}</p>

                    {/* Actions on hover */}
                    <div className="flex gap-2 mt-2 opacity-0 group-hover:opacity-100 transition">
                      <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); handleEditEvent(event); }}>
                        Edit
                      </Button>
                      <Button variant="danger" size="sm" onClick={(e) => { e.stopPropagation(); handleDeleteEvent(event.id); }}>
                        Delete
                      </Button>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </Card>

        {/* Event detail panel */}
        {selectedEvent && (
          <Card className="w-96 flex-shrink-0 p-5 overflow-y-auto flex flex-col gap-4">
            <div>
              <h2 className="text-xl font-bold text-txt">{selectedEvent.title}</h2>
              <div className="flex gap-2 items-center mt-1">
                <span className="text-txt-muted text-sm">{selectedEvent.date || 'No date'}</span>
                <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                  categoryColors[selectedEvent.category] || categoryColors.event
                }`}>
                  {selectedEvent.category}
                </span>
              </div>
            </div>

            <div className="border-t border-txt-muted/10 pt-3">
              <p className="text-sm text-txt whitespace-pre-wrap leading-relaxed">
                {selectedEvent.description || 'No description'}
              </p>
            </div>

            {selectedEvent.meta && Object.keys(selectedEvent.meta).filter(k => k !== 'event_date' && k !== 'category').length > 0 && (
              <div className="border-t border-txt-muted/10 pt-3">
                <p className="text-xs font-bold text-txt-muted uppercase tracking-wider mb-2">Metadata</p>
                <div className="space-y-1">
                  {Object.entries(selectedEvent.meta)
                    .filter(([k]) => k !== 'event_date' && k !== 'category')
                    .map(([k, v]) => (
                      <div key={k} className="flex justify-between text-xs">
                        <span className="text-txt-muted">{k}</span>
                        <span className="text-txt">{v}</span>
                      </div>
                    ))}
                </div>
              </div>
            )}

            <div className="mt-auto pt-3 border-t border-txt-muted/10 flex gap-2">
              <Button variant="secondary" size="sm" onClick={() => handleEditEvent(selectedEvent)}>
                Edit
              </Button>
              <Button variant="danger" size="sm" onClick={() => handleDeleteEvent(selectedEvent.id)}>
                Delete
              </Button>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
