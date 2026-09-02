// Shared skill helpers, kept out of the component files so those export only
// components (which is what lets React Fast Refresh work on them).

// Band on the same rounded number the label shows. Comparing the raw value
// against the threshold made 24.98 render as "25.0" in stale red right next
// to a genuine 25.3 in fading amber, which just looks broken.
//
// These boundaries mirror FRESH_THRESHOLD / FADING_THRESHOLD in scoring.py.
// The API's forecast counts down to the same numbers, so a card saying "goes
// stale in 12 days" turns amber on exactly the day it predicted.
export const shown = (freshness) => Number(freshness.toFixed(1));

export function band(freshness) {
  const value = shown(freshness);
  if (value >= 60) return "fresh";
  if (value >= 25) return "fading";
  return "stale";
}

// The skill worth naming is not the worst one -- something you touched twice
// and abandoned is meant to be at zero. It is the one with real investment
// behind it that is closest to slipping out of its band: high depth, low
// remaining runway. That is the drift you can still do something about.
export function mostAtRisk(skills) {
  const candidates = skills.filter(
    (s) => s.depth != null && s.depth >= 20 && band(s.freshness) !== "stale",
  );
  if (!candidates.length) return null;

  return candidates.reduce((worst, s) => {
    const runway = s.days_until_stale ?? Infinity;
    const worstRunway = worst.days_until_stale ?? Infinity;
    return runway < worstRunway ? s : worst;
  });
}
