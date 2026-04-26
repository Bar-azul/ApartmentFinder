import { useState } from "react";
import axios from "axios";
import "./App.css";

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

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

function formatPrice(price) {
  if (price === null || price === undefined || price === "") return "מחיר לא צוין";
  const numericPrice = Number(price);
  if (Number.isNaN(numericPrice)) return "מחיר לא צוין";
  return `₪ ${numericPrice.toLocaleString("he-IL")}`;
}

function getYad2Url(apartment) {
  if (apartment?.yad2_url) return apartment.yad2_url;

  if (apartment?.token) {
    return `https://www.yad2.co.il/realestate/item/center-and-sharon/${apartment.token}`;
  }

  return "https://www.yad2.co.il/realestate/rent";
}

function App() {
  const [prompt, setPrompt] = useState(
    "חפש לי דירה בראשון לציון עם מרפסת מ-4000 עד 5500 שקל, בין 2.5 ל-4 חדרים"
  );

  const [selectedMustHave, setSelectedMustHave] = useState([]);
  const [apartments, setApartments] = useState([]);
  const [filters, setFilters] = useState(null);
  const [showFilters, setShowFilters] = useState(false);

  const [selectedApartment, setSelectedApartment] = useState(null);
  const [expandedImage, setExpandedImage] = useState(null);

  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");

  function toggleMustHave(featureKey) {
    setSelectedMustHave((prev) =>
      prev.includes(featureKey)
        ? prev.filter((key) => key !== featureKey)
        : [...prev, featureKey]
    );
  }

  function clearMustHave() {
    setSelectedMustHave([]);
  }

  async function handleSearch() {
    setLoading(true);
    setProgress(0);
    setError("");
    setApartments([]);
    setFilters(null);
    setShowFilters(false);
    setSelectedApartment(null);
    setExpandedImage(null);

    let pollTimer = null;

    try {
      const startResponse = await axios.post(`${API_BASE_URL}/api/search/start`, {
        prompt,
        must_have: selectedMustHave,
      });

      const jobId = startResponse.data.job_id;

      pollTimer = setInterval(async () => {
        try {
          const progressResponse = await axios.get(
            `${API_BASE_URL}/api/search/progress/${jobId}`
          );

          const job = progressResponse.data;
          setProgress(job.progress || 0);

          if (job.done) {
            clearInterval(pollTimer);

            if (job.success && job.result) {
              setProgress(100);
              setApartments(job.result.apartments || []);
              setFilters(job.result.filters || null);
            } else {
              setError(job.error || "שגיאה בחיפוש");
            }

            setTimeout(() => {
              setLoading(false);
              setProgress(0);
            }, 700);
          }
        } catch (err) {
          clearInterval(pollTimer);
          setError(err.message || "שגיאה בבדיקת התקדמות");
          setLoading(false);
          setProgress(0);
        }
      }, 800);
    } catch (err) {
      if (pollTimer) clearInterval(pollTimer);

      setError(err.response?.data?.detail || err.message || "שגיאה בהתחלת החיפוש");
      setLoading(false);
      setProgress(0);
    }
  }

  function handleOpenInYad2(apartment) {
    const url = getYad2Url(apartment);
    window.open(url, "_blank", "noopener,noreferrer");
  }

  return (
    <div className="page" dir="rtl">
      <header className="hero">
        <h1>ApartmentFinder</h1>
        <p>חיפוש דירות חכם באמצעות Prompt + Yad2 API</p>
      </header>

      <section className="search-box">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="לדוגמה: חפש לי דירה בהרצליה עד 3500 שקל עם 2 חדרים"
        />

        <button onClick={handleSearch} disabled={loading}>
          {loading ? "מחפש..." : "חפש דירות"}
        </button>
      </section>

      <FeatureLegend
        selectedMustHave={selectedMustHave}
        onToggle={toggleMustHave}
        onClear={clearMustHave}
      />

      {loading && <SearchProgress progress={progress} />}

      {error && <div className="error">{error}</div>}

      {filters && (
        <section className="filters-toggle-box">
          <button
            type="button"
            className="filters-toggle-button"
            onClick={() => setShowFilters((prev) => !prev)}
          >
            {showFilters
              ? "הסתר פילטרים שהמערכת הבינה"
              : "הצג פילטרים שהמערכת הבינה"}
            <span>{showFilters ? "▲" : "▼"}</span>
          </button>

          {showFilters && (
            <div className="filters-box">
              <h3>פילטרים שהמערכת הבינה</h3>
              <pre>{JSON.stringify(filters, null, 2)}</pre>
            </div>
          )}
        </section>
      )}

      <section className="results-header">
        <h2>תוצאות</h2>
        <span>{apartments.length} דירות נמצאו</span>
      </section>

      <section className="grid">
        {apartments.map((apartment) => (
          <ApartmentCard
            key={`${apartment.order_id}-${apartment.token}`}
            apartment={apartment}
            onOpen={() => setSelectedApartment(apartment)}
          />
        ))}
      </section>

      {selectedApartment && (
        <ApartmentModal
          apartment={selectedApartment}
          onClose={() => setSelectedApartment(null)}
          onImageOpen={setExpandedImage}
          onOpenInYad2={() => handleOpenInYad2(selectedApartment)}
        />
      )}

      {expandedImage && (
        <div className="image-lightbox" onClick={() => setExpandedImage(null)}>
          <button
            className="lightbox-close"
            onClick={() => setExpandedImage(null)}
          >
            ×
          </button>

          <img
            src={expandedImage}
            alt="expanded"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </div>
  );
}

function FeatureLegend({ selectedMustHave, onToggle, onClear }) {
  return (
    <section className="feature-legend">
      <div className="feature-legend-title">
        <h3>מאפיינים שניתן לסנן לפיהם</h3>
        <p>אפשר לכתוב אותם בפרומפט או פשוט ללחוץ על הכרטיסיות כאן ולסמן.</p>

        {!!selectedMustHave.length && (
          <button className="clear-features-button" onClick={onClear}>
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
              className={`feature-legend-item ${selected ? "selected" : ""}`}
              key={feature.key}
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

function SearchProgress({ progress }) {
  return (
    <div className="search-progress">
      <div className="progress-header">
        <span>מחפש ומעשיר מודעות...</span>
        <strong>{progress}%</strong>
      </div>

      <div className="progress-track">
        <div className="progress-fill" style={{ width: `${progress}%` }} />
      </div>

      <div className="progress-steps">
        <span className={progress >= 15 ? "active" : ""}>Map API</span>
        <span className={progress >= 45 ? "active" : ""}>פתיחת מודעות</span>
        <span className={progress >= 75 ? "active" : ""}>זיהוי מאפיינים</span>
        <span className={progress >= 100 ? "active" : ""}>סיום</span>
      </div>
    </div>
  );
}

function ApartmentCard({ apartment, onOpen }) {
  const image =
    apartment.cover_image ||
    apartment.images?.[0] ||
    "https://placehold.co/600x400?text=No+Image";

  return (
    <article className="card">
      <img src={image} alt="apartment" />

      <div className="card-content">
        <div className="price">{formatPrice(apartment.price)}</div>

        <h3>
          {apartment.property_type || "נכס"} · {apartment.rooms || "-"} חדרים
        </h3>

        <p className="location">
          {apartment.city || ""}
          {apartment.neighborhood ? `, ${apartment.neighborhood}` : ""}
        </p>

        <p>
          {apartment.street || ""} {apartment.house_number || ""}
        </p>

        <div className="meta">
          <span>{apartment.square_meter || "-"} מ״ר</span>
          <span>קומה {apartment.floor ?? "-"}</span>
        </div>

        <FeatureBadges features={apartment.features} compact />

        <button className="details-link-button" onClick={onOpen}>
          פתח מודעה
        </button>
      </div>
    </article>
  );
}

function ApartmentModal({ apartment, onClose, onImageOpen, onOpenInYad2 }) {
  const images = apartment.images?.length
    ? apartment.images
    : apartment.cover_image
      ? [apartment.cover_image]
      : [];

  const description =
    apartment.description || apartment.text || apartment.title || "אין תיאור זמין.";

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>
          ×
        </button>

        <div className="modal-gallery">
          {images.length ? (
            images.map((img, index) => (
              <img
                key={`${img}-${index}`}
                src={img}
                alt={`img-${index}`}
                onClick={() => onImageOpen(img)}
              />
            ))
          ) : (
            <div className="no-image">אין תמונות</div>
          )}
        </div>

        <div className="modal-content">
          <h2>{formatPrice(apartment.price)}</h2>

          <h3>
            {apartment.property_type || "נכס"} · {apartment.rooms || "-"} חדרים ·{" "}
            {apartment.square_meter || "-"} מ״ר
          </h3>

          <FeatureBadges features={apartment.features} />

          <div className="description-box">
            <h4>תיאור</h4>
            <p>{description}</p>
          </div>

          <div className="modal-details-grid">
            <p><strong>עיר:</strong> {apartment.city || "-"}</p>
            <p><strong>שכונה:</strong> {apartment.neighborhood || "-"}</p>
            <p>
              <strong>רחוב:</strong> {apartment.street || "-"}{" "}
              {apartment.house_number || ""}
            </p>
            <p><strong>קומה:</strong> {apartment.floor ?? "-"}</p>
            <p><strong>מספר מודעה:</strong> {apartment.order_id || "-"}</p>
          </div>

          <div className="modal-actions">
            {apartment.lat && apartment.lon && (
              <a
                className="map-link"
                href={`https://www.google.com/maps?q=${apartment.lat},${apartment.lon}`}
                target="_blank"
                rel="noreferrer"
              >
                פתח מיקום במפה
              </a>
            )}

            <button className="open-yad2-button" onClick={onOpenInYad2}>
              לפתיחה ביד 2
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function FeatureBadges({ features, compact = false }) {
  if (!features) return null;

  const active = FILTERABLE_FEATURES.filter((item) => features[item.key]);

  if (!active.length) {
    return compact ? null : (
      <div className="features-empty">לא נמצאו מאפיינים מיוחדים</div>
    );
  }

  return (
    <div className={compact ? "features-row compact" : "features-row"}>
      {active.map((item) => (
        <span key={item.key} className="feature-badge">
          {item.label}
        </span>
      ))}
    </div>
  );
}

export default App;