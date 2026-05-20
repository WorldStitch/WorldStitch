/**
 * WikiLink TipTap Mark extension.
 *
 * Detects [[text]] patterns as the user types and converts them to styled
 * inline chips with accent color. On completion (the closing ]] triggers it),
 * calls the relationships API to record the link from the current note.
 * Clicking a chip calls onNavigate(label).
 *
 * Usage:
 *   const ext = createWikiLinkExtension({ noteIdRef, onNavigate })
 *   // then add `ext` to the TipTap extensions array
 */

import { Mark, markInputRule } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import { notes as notesApi } from '@/api';

const WikiLinkPluginKey = new PluginKey('wikiLink');

/**
 * @param {Object} opts
 * @param {{ current: string|null }} opts.noteIdRef  — mutable ref to current note id
 * @param {(label: string) => void} opts.onNavigate  — called when chip is clicked
 */
export function createWikiLinkExtension({ noteIdRef, onNavigate } = {}) {
  // Track which (noteId, label) pairs have already been sent to avoid duplicates
  // within a single editor session. Keyed as "noteId::label".
  const seen = new Set();

  async function fireRelationshipApi(label) {
    const noteId = noteIdRef?.current;
    if (!noteId || !label) return;
    const key = `${noteId}::${label.toLowerCase()}`;
    if (seen.has(key)) return;
    seen.add(key);
    try {
      await notesApi.createRelationship(noteId, label);
    } catch {
      // Best-effort — wiki-link rendering still works even if the API fails
    }
  }

  return Mark.create({
    name: 'wikiLink',

    // Prevent the mark from extending when more text is typed after it
    inclusive: false,

    addAttributes() {
      return {
        label: {
          default: null,
          parseHTML: (el) => el.getAttribute('data-label'),
          renderHTML: (attrs) => {
            if (!attrs.label) return {};
            return { 'data-label': attrs.label };
          },
        },
      };
    },

    parseHTML() {
      return [{ tag: 'span[data-wiki-link]' }];
    },

    renderHTML({ HTMLAttributes }) {
      return [
        'span',
        {
          'data-wiki-link': '',
          class:
            'wiki-link text-accent underline underline-offset-2 cursor-pointer ' +
            'bg-accent/8 hover:bg-accent/20 rounded px-0.5 transition-colors',
          ...HTMLAttributes,
        },
        0,
      ];
    },

    addInputRules() {
      return [
        markInputRule({
          // Captures the full [[text]] including brackets as $1
          find: /(\[\[[^\]]+\]\])$/,
          type: this.type,
          getAttributes: (match) => {
            const full = match[1]; // "[[text]]"
            const label = full.slice(2, -2); // "text"
            // Defer API call so it doesn't block the ProseMirror transaction
            setTimeout(() => fireRelationshipApi(label), 0);
            return { label };
          },
        }),
      ];
    },

    addProseMirrorPlugins() {
      return [
        new Plugin({
          key: WikiLinkPluginKey,
          props: {
            handleClick(_view, _pos, event) {
              const el = event.target?.closest?.('[data-wiki-link]');
              if (!el) return false;
              const label = el.getAttribute('data-label');
              if (label && onNavigate) {
                onNavigate(label);
                return true;
              }
              return false;
            },
          },
        }),
      ];
    },
  });
}
