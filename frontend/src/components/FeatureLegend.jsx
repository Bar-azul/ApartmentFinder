const FILTERABLE_FEATURES = [
  { key: "mamad", label: "ממ״ד", example: "עם ממד / ממ״ד" },
  { key: "elevator", label: "מעלית", example: "עם מעלית" },
  { key: "parking", label: "חניה", example: "עם חניה / חנייה" },
  { key: "balcony", label: "מרפסת", example: "עם מרפסת" },
  { key: "furniture", label: "ריהוט", example: "מרוהטת / עם ריהוט" },
  { key: "pets_allowed", label: "בעלי חיים", example: "עם בעלי חיים / כלב / חתול" },
  { key: "air_conditioner", label: "מיזוג", example: "עם מזגן / מיזוג" },
  { key: "renovated", label: "משופצת", example: "דירה משופצת" },
  { key: "immediate_entrance", label: "כניסה מיידית", example: "כניסה מיידית" },
  { key: "building_shelter", label: "מקלט", example: "עם מקלט" },
];

function FeatureLegend({ selectedMustHave, onToggle, onClear }) {
  return (
    <section className="feature-legend">
      <div className="feature-legend-title">
        <h3>מאפיינים שניתן לסנן לפיהם</h3>
        <p>אפשר לכתוב אותם בפרומפט או פשוט ללחוץ על הכרטיסיות כאן ולסמן.</p>

        {!!selectedMustHave.length && (
          <button
            type="button"
            className="clear-features-button"
            onClick={onClear}
          >
            נקה סימונים
          </button>
        )}
      </div>

      <div className="feature-legend-grid">
        {FILTERABLE_FEATURES.map((feature) => {
          const selected = selectedMustHave.includes(feature.key);

          return (
            <button
              type="button"
              key={feature.key}
              className={`feature-legend-item ${selected ? "selected" : ""}`}
              onClick={() => onToggle(feature.key)}
              aria-pressed={selected}
            >
              <span className="feature-legend-badge">{feature.label}</span>
              <small>{feature.example}</small>
              {selected && <span className="selected-mark">✓ מסומן</span>}
            </button>
          );
        })}
      </div>
    </section>
  );
}

export { FILTERABLE_FEATURES };
export default FeatureLegend;