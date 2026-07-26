"use client";

import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

// ── ThemeToggle ────────────────────────────────────────────────────
// Renders a ☀️ / 🌙 button that switches between dark and light themes.
// The `mounted` guard is mandatory: useTheme() returns undefined during SSR,
// so we defer rendering until after client hydration to prevent mismatches.

export default function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    // Reserve space so layout doesn't shift on hydration
    return <div className="theme-toggle-placeholder" aria-hidden />;
  }

  const isDark = theme === "dark";

  return (
    <button
      id="theme-toggle"
      className="theme-toggle"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      title={isDark ? "Switch to Light Mode" : "Switch to Dark Mode"}
      aria-label={isDark ? "Switch to Light Mode" : "Switch to Dark Mode"}
    >
      <span className="theme-toggle-icon" aria-hidden>
        {isDark ? "☀️" : "🌙"}
      </span>
      <span className="theme-toggle-label">
        {isDark ? "Light Mode" : "Dark Mode"}
      </span>
    </button>
  );
}
