/**
 * Theme management for WorldStitch.
 *
 * Themes are applied by setting `data-theme` on <html>.
 * Each theme maps to a set of CSS custom properties in index.css.
 */

export const THEMES = [
  {
    id: "dark",
    label: "Dark",
    description: "Deep dark with purple accents",
    preview: { bg: "#0D0D14", accent: "#7C5CFC", card: "#1E1E2A", text: "#ECEEF4" },
  },
  {
    id: "light",
    label: "Light",
    description: "Clean white with violet accents",
    preview: { bg: "#F5F5FA", accent: "#6348DC", card: "#FFFFFF", text: "#1C1C28" },
  },
  {
    id: "midnight",
    label: "Midnight Blue",
    description: "Deep navy with cool blue accents",
    preview: { bg: "#0C111D", accent: "#60A5FA", card: "#161F34", text: "#E2E8F5" },
  },
  {
    id: "forest",
    label: "Forest",
    description: "Rich greens with emerald accents",
    preview: { bg: "#0C1410", accent: "#34D399", card: "#18261E", text: "#DEEEE4" },
  },
  {
    id: "parchment",
    label: "Parchment",
    description: "Warm sepia tones, old-world feel",
    preview: { bg: "#F2EBDC", accent: "#A05A2C", card: "#FFFAF0", text: "#3A2A1C" },
  },
];

/**
 * Apply a theme by ID. Sets `data-theme` on documentElement
 * and briefly enables a CSS transition class for smooth switching.
 */
export function applyTheme(themeId) {
  const html = document.documentElement;

  // Only animate if switching from a different theme
  const current = html.getAttribute("data-theme");
  if (current && current !== themeId) {
    html.classList.add("theme-transition");
  }

  // Apply theme immediately
  html.setAttribute("data-theme", themeId);

  // Store preference
  try {
    localStorage.setItem("WorldStitch-theme", themeId);
  } catch {
    // localStorage may be unavailable
  }

  // Remove transition class after animation completes
  requestAnimationFrame(() => {
    setTimeout(() => {
      html.classList.remove("theme-transition");
    }, 300);
  });
}

/**
 * Get the currently stored theme preference.
 */
export function getStoredTheme() {
  try {
    return localStorage.getItem("WorldStitch-theme") || "dark";
  } catch {
    return "dark";
  }
}

/**
 * Initialize theme on app startup.
 */
export function initTheme() {
  const themeId = getStoredTheme();
  document.documentElement.setAttribute("data-theme", themeId);
  return themeId;
}
