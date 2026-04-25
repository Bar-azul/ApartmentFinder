import { useState } from "react";
import axios from "axios";
import "./App.css";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

function formatPrice(price) {
  if (price === null || price === undefined || price === "") return "מחיר לא צוין";

  const numericPrice = Number(price);
  if (Number.isNaN(numericPrice)) return "מחיר לא צוין";

  return `₪ ${numericPrice.toLocaleString("he-IL")}`;
}

function App() {
  const [prompt, setPrompt] = useState(
    "חפש לי דירה בהרצליה, פתח תקווה, קרית אונו, רעננה, כפר סבא ממד מ-4000 עד 5500 שקל, בין 2.5 ל-4 חדרים"
  );

  const [apartments, setApartments] = useState([]);
  const [filters, setFilters] = useState(null);

  const [selectedApartment, setSelectedApartment] = useState(null);
  const [expandedImage, setExpandedImage] = useState(null);

  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");

  async function handleSearch() {
    setLoading(true);
    setProgress(0);
    setError("");
    setApartments([]);
    setFilters(null);
    setSelectedApartment(null);
    setExpandedImage(null);

    const progressTimer = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 95) return prev;
        const next = prev + Math.floor(Math.random() * 6) + 2;
        return next > 95 ? 95 : next;
      });
    }, 700);

    try {
      const response = await axios.post(`${API_BASE_URL}/api/search/prompt`, {
        prompt,
      });

      setProgress(100);

      setTimeout(() => {
        setApartments(response.data.apartments || []);
        setFilters(response.data.filters || null);
      }, 300);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "שגיאה בחיפוש");
    } finally {
      clearInterval(progressTimer);

      setTimeout(() => {
        setLoading(false);
        setProgress(0);
      }, 800);
    }
  }

  async function handleOpenInYad2(apartment) {
    try {
      await axios.post(`${API_BASE_URL}/api/search/open-browser`, apartment);
    } catch (err) {
      console.error("open browser error", err);
    }
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

      {loading && <SearchProgress progress={progress} />}

      {error && <div className="error">{error}</div>}

      {filters && (
        <section className="filters-box">
          <h3>פילטרים שהמערכת הבינה</h3>
          <pre>{JSON.stringify(filters, null, 2)}</pre>
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
            <p><strong>Token:</strong> {apartment.token || "-"}</p>
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

  const items = [
    { key: "mamad", label: "ממ״ד" },
    { key: "elevator", label: "מעלית" },
    { key: "parking", label: "חניה" },
    { key: "air_conditioner", label: "מיזוג" },
    { key: "balcony", label: "מרפסת" },
    { key: "furniture", label: "ריהוט" },
    { key: "renovated", label: "משופצת" },
    { key: "pets_allowed", label: "בעלי חיים" },
  ];

  const active = items.filter((item) => features[item.key]);

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