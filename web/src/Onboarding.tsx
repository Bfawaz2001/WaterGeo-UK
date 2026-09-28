import { useState } from "react";

const STORAGE_KEY = "watergeo-explorer-introduction-v1";

export function Onboarding() {
  const [visible, setVisible] = useState(() => window.localStorage.getItem(STORAGE_KEY) !== "dismissed");
  if (!visible) return null;
  const dismiss = () => {
    window.localStorage.setItem(STORAGE_KEY, "dismissed");
    setVisible(false);
  };
  return (
    <aside className="onboarding" aria-labelledby="onboarding-heading">
      <button type="button" className="icon-button" onClick={dismiss} aria-label="Dismiss explorer introduction">×</button>
      <p className="eyebrow">Welcome to WaterGeo UK</p>
      <h2 id="onboarding-heading">Explore public water data in context</h2>
      <ol>
        <li><strong>Search</strong><span>Find a station, reservoir, Water Body or company.</span></li>
        <li><strong>Explore</strong><span>Switch layers on and move the map to refresh nearby results.</span></li>
        <li><strong>Inspect</strong><span>Select a feature to see its values, timing and source.</span></li>
      </ol>
      <button type="button" className="primary-button" onClick={dismiss}>Start exploring</button>
    </aside>
  );
}
