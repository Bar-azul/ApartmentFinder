import FeatureBadges from "./FeatureBadges";
import VerificationBadge from "./VerificationBadge";

function formatPrice(price) {
  if (!price) return "מחיר לא צוין";
  return `₪ ${Number(price).toLocaleString("he-IL")}`;
}

function ApartmentCard({ apartment, onOpen, onOpenBrowser }) {
  const image =
    apartment.cover_image ||
    apartment.images?.[0] ||
    "https://placehold.co/600x400?text=No+Image";

  return (
    <article className="apartment-card">
      <div className="apartment-image-wrap">
        <img
          src={image}
          alt={apartment.street || apartment.city || "apartment"}
          className="apartment-image"
          loading="lazy"
        />

        <VerificationBadge apartment={apartment} />
      </div>

      <div className="apartment-content">
        <div className="apartment-price">{formatPrice(apartment.price)}</div>

        <div className="apartment-main-line">
          {apartment.rooms || "-"} חדרים
          {apartment.property_type ? ` • ${apartment.property_type}` : ""}
        </div>

        <div className="apartment-location">
          {[apartment.street, apartment.house_number].filter(Boolean).join(" ")}
          {apartment.city ? `, ${apartment.city}` : ""}
        </div>

        <div className="apartment-meta-pills">
          {!!apartment.square_meter && (
            <span className="meta-pill">{apartment.square_meter} מ״ר</span>
          )}

          {apartment.floor !== null && apartment.floor !== undefined && (
            <span className="meta-pill">קומה {apartment.floor}</span>
          )}
        </div>

        <FeatureBadges features={apartment.features} compact />

        <div className="apartment-actions">
          <button type="button" className="primary-btn" onClick={onOpen}>
            פתח מודעה
          </button>

          <button type="button" className="secondary-btn" onClick={onOpenBrowser}>
            פתח ביד 2
          </button>
        </div>
      </div>
    </article>
  );
}

export default ApartmentCard;