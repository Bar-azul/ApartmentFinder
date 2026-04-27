const FEATURE_LABELS = {
  elevator: "מעלית",
  parking: "חניה",
  mamad: "ממ״ד",
  air_conditioner: "מיזוג",
  balcony: "מרפסת",
  furniture: "ריהוט",
  renovated: "משופצת",
  pets_allowed: "בעלי חיים",
  immediate_entrance: "כניסה מיידית",
  building_shelter: "מקלט",
};

function FeatureBadges({
  features,
  compact = true,
  emptyText = "לא זוהו מאפיינים",
}) {
  if (!features) {
    return (
      <div
        className={`features-row ${
          compact ? "compact" : ""
        }`}
      >
        <span className="features-empty">
          {emptyText}
        </span>
      </div>
    );
  }

  const activeFeatures = Object.entries(FEATURE_LABELS)
    .filter(([key]) => features[key])
    .map(([, label]) => label);

  if (activeFeatures.length === 0) {
    return (
      <div
        className={`features-row ${
          compact ? "compact" : ""
        }`}
      >
        <span className="features-empty">
          {emptyText}
        </span>
      </div>
    );
  }

  return (
    <div
      className={`features-row ${
        compact ? "compact" : ""
      }`}
    >
      {activeFeatures.map((label) => (
        <span
          key={label}
          className="feature-badge"
        >
          {label}
        </span>
      ))}
    </div>
  );
}

export default FeatureBadges;