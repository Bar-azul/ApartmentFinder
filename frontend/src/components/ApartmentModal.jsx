import FeatureBadges from "./FeatureBadges";
import VerificationBadge from "./VerificationBadge";

function formatPrice(price) {
  if (!price) return "לא צוין";
  return `${Number(price).toLocaleString()} ₪`;
}

function ApartmentModal({
  apartment,
  onClose,
  onOpenBrowser,
  onImageClick,
}) {
  if (!apartment) return null;

  const images =
    apartment.images?.length > 0
      ? apartment.images
      : apartment.cover_image
      ? [apartment.cover_image]
      : [];

  return (
    <div
      className="modal-overlay"
      onClick={onClose}
    >
      <div
        className="modal-card"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          className="modal-close-btn"
          onClick={onClose}
        >
          ✕
        </button>

        <div className="modal-header">
          <div>
            <div className="modal-price">
              {formatPrice(apartment.price)}
            </div>

            <div className="modal-subtitle">
              {apartment.rooms || "-"} חדרים
              {apartment.property_type
                ? ` • ${apartment.property_type}`
                : ""}
            </div>

            <div className="modal-location">
              {[
                apartment.street,
                apartment.house_number,
              ]
                .filter(Boolean)
                .join(" ")}
              {apartment.city
                ? `, ${apartment.city}`
                : ""}
            </div>
          </div>

          <VerificationBadge apartment={apartment} />
        </div>

        {images.length > 0 && (
          <div className="modal-gallery">
            {images.map((img, index) => (
              <img
                key={index}
                src={img}
                alt={`image-${index}`}
                className="modal-gallery-image"
                onClick={() => onImageClick(img)}
              />
            ))}
          </div>
        )}

        <div className="modal-section">
          <h3>מאפיינים</h3>
          <FeatureBadges
            features={apartment.features}
            compact={false}
          />
        </div>

        <div className="modal-section">
          <h3>פרטי הנכס</h3>

          <div className="modal-details-grid">
            <div>
              <strong>מ״ר:</strong>{" "}
              {apartment.square_meter || "-"}
            </div>

            <div>
              <strong>קומה:</strong>{" "}
              {apartment.floor || "-"}
            </div>

            <div>
              <strong>שכונה:</strong>{" "}
              {apartment.neighborhood || "-"}
            </div>

            <div>
              <strong>עיר:</strong>{" "}
              {apartment.city || "-"}
            </div>
          </div>
        </div>

        <div className="modal-section">
          <h3>תיאור</h3>

          <p className="modal-description">
            {apartment.description ||
              "אין תיאור זמין כרגע."}
          </p>
        </div>

        <div className="modal-actions">
          <button
            type="button"
            className="primary-btn"
            onClick={() => onOpenBrowser(apartment)}
          >
            פתח ביד2
          </button>

          <button
            type="button"
            className="secondary-btn"
            onClick={onClose}
          >
            סגור
          </button>
        </div>
      </div>
    </div>
  );
}

export default ApartmentModal;