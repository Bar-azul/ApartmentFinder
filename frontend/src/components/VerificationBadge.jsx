function VerificationBadge({ apartment }) {
  if (!apartment) return null;

  const status = apartment.verification_status;
  const reason = apartment.verification_reason || "";

  if (status === "verified") {
    return (
      <div
        className="verification-badge verified"
        title={reason}
      >
        ✓ אומת
      </div>
    );
  }

  if (status === "unverified") {
    return (
      <div
        className="verification-badge unverified"
        title={reason}
      >
        ⚠ לא אומת
      </div>
    );
  }

  if (status === "checking") {
    return (
      <div
        className="verification-badge checking"
        title="נמצא כרגע בתהליך אימות"
      >
        ⏳ בבדיקה
      </div>
    );
  }

  if (status === "rejected") {
    return (
      <div
        className="verification-badge rejected"
        title={reason}
      >
        ✕ לא מתאים
      </div>
    );
  }

  return null;
}

export default VerificationBadge;