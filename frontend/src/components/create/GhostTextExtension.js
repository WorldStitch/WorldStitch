import { Extension } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import { Decoration, DecorationSet } from '@tiptap/pm/view';

const GhostTextKey = new PluginKey('ghostText');

/**
 * Creates a TipTap extension for ghost text AI continuations.
 *
 * @param {Object} opts
 * @param {React.MutableRefObject<boolean>} opts.enabledRef  - ref that tracks whether co-pilot is active
 * @param {React.MutableRefObject<Function|null>} opts.onGetSuggestionRef - ref to async (text, signal) => string
 */
export function createGhostTextExtension({ enabledRef, onGetSuggestionRef }) {
  return Extension.create({
    name: 'ghostText',

    addProseMirrorPlugins() {
      return [
        new Plugin({
          key: GhostTextKey,

          // Plugin state: { suggestion: string|null, decorationPos: number|null }
          state: {
            init() {
              return { suggestion: null, decorationPos: null };
            },
            apply(tr, prev) {
              const meta = tr.getMeta(GhostTextKey);
              if (meta !== undefined) return meta;
              // Any document change clears the ghost text
              if (tr.docChanged) return { suggestion: null, decorationPos: null };
              return prev;
            },
          },

          props: {
            handleKeyDown(view, event) {
              if (!enabledRef?.current) return false;
              const pluginState = GhostTextKey.getState(view.state);
              if (!pluginState?.suggestion) return false;

              if (event.key === 'Tab') {
                event.preventDefault();
                const { tr } = view.state;
                // Insert the ghost text at the decoration position
                tr.insertText(pluginState.suggestion, pluginState.decorationPos);
                view.dispatch(
                  tr.setMeta(GhostTextKey, { suggestion: null, decorationPos: null })
                );
                return true;
              }

              if (event.key === 'Escape') {
                view.dispatch(
                  view.state.tr.setMeta(GhostTextKey, { suggestion: null, decorationPos: null })
                );
                return true;
              }

              return false;
            },

            decorations(state) {
              const pluginState = GhostTextKey.getState(state);
              if (!pluginState?.suggestion || pluginState.decorationPos === null) {
                return DecorationSet.empty;
              }

              const widget = Decoration.widget(
                pluginState.decorationPos,
                () => {
                  const span = document.createElement('span');
                  span.className = 'ghost-text-suggestion';
                  span.setAttribute('data-ghost-text', 'true');
                  span.textContent = ' ' + pluginState.suggestion;
                  return span;
                },
                { side: 1, key: 'ghost-suggestion' }
              );

              return DecorationSet.create(state.doc, [widget]);
            },
          },

          view(editorView) {
            let debounceTimer = null;
            let abortController = null;

            return {
              update(view, prevState) {
                // Always clear timer on any editor update
                clearTimeout(debounceTimer);
                abortController?.abort();
                abortController = null;

                if (!enabledRef?.current) {
                  // Clear any lingering suggestion
                  const ps = GhostTextKey.getState(view.state);
                  if (ps?.suggestion) {
                    view.dispatch(
                      view.state.tr.setMeta(GhostTextKey, { suggestion: null, decorationPos: null })
                    );
                  }
                  return;
                }

                const { state } = view;

                // Only trigger when selection changes or document changes
                const selChanged = !state.selection.eq(prevState.selection);
                const docChanged = !state.doc.eq(prevState.doc);
                if (!selChanged && !docChanged) return;

                // No suggestions when there's a text selection
                if (!state.selection.empty) return;

                const { $head } = state.selection;

                // Only suggest at end of a paragraph
                if ($head.parent.type.name !== 'paragraph') return;
                if ($head.parentOffset !== $head.parent.content.size) return;

                const text = $head.parent.textContent.trim();
                // Need at least 15 chars to make a meaningful suggestion
                if (text.length < 15) return;

                const capturedPos = $head.pos;
                const capturedText = $head.parent.textContent;

                debounceTimer = setTimeout(async () => {
                  const getSuggestion = onGetSuggestionRef?.current;
                  if (!getSuggestion) return;
                  if (!enabledRef?.current) return;

                  const controller = new AbortController();
                  abortController = controller;

                  try {
                    const suggestion = await getSuggestion(capturedText, controller.signal);
                    if (!suggestion || controller.signal.aborted) return;
                    if (!enabledRef?.current) return;

                    // Verify cursor hasn't moved since we started
                    const currentHead = view.state.selection.$head;
                    if (currentHead.pos !== capturedPos) return;

                    view.dispatch(
                      view.state.tr.setMeta(GhostTextKey, {
                        suggestion: suggestion.trim(),
                        decorationPos: capturedPos,
                      })
                    );
                  } catch {
                    // Silently ignore aborts and API errors
                  }
                }, 1500);
              },

              destroy() {
                clearTimeout(debounceTimer);
                abortController?.abort();
              },
            };
          },
        }),
      ];
    },
  });
}
