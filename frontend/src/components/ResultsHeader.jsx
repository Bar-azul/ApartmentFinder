function ResultsHeader({
  apartmentsCount,
  verificationStats,
  isSearching,
  loading,
}) {
  const stats = verificationStats || {};

  const total = stats.total || 0;
  const checked = stats.checked || 0;
  const verified = stats.verified || 0;
  const rejected = stats.rejected || 0;
  const failed = stats.failed || 0;
  const done = !!stats.done;
  const fallbackMode = !!stats.fallback_mode;

  const inProgress = !done && checked < total;
  const progressPercent =
    total > 0 ? Math.min(100, Math.round((checked / total) * 100)) : 0;

  const showVerification =
    total > 0 || verified > 0 || rejected > 0 || failed > 0;

  return (
    <section className="results-header">
      <div className="results-header-top">
        <h2>{apartmentsCount} דירות מוצגות</h2>

        {(loading || isSearching) && (
          <div className="thinking-inline">
            <span className="spinner-ring" />
            <span>מחפש עבורך מודעות...</span>
          </div>
        )}
      </div>

      {showVerification && (
        <div className="verification-panel">
          {!done && !fallbackMode && (
            <>
              <div className="verification-row">
                <span className="verification-title">
                  מאמת מודעות ברקע...
                </span>

                <span className="verification-percent">
                  {progressPercent}%
                </span>
              </div>

              <div className="verification-progress-track">
                <div
                  className="verification-progress-fill"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>

              <div className="verification-meta">
                נבדקו {checked} מתוך {total}
              </div>
            </>
          )}

          {done && !fallbackMode && (
            <>
              <div className="verification-row">
                <span className="verification-title success">
                  האימות הסתיים
                </span>
              </div>

              <div className="verification-summary">
                <span>אומתו: {verified}</span>
                <span>נפסלו: {rejected}</span>
                {failed > 0 && <span>נכשלו: {failed}</span>}
              </div>
            </>
          )}

          {fallbackMode && (
            <>
              <div className="verification-row">
                <span className="verification-title warning">
                  לא הצלחנו להשלים אימות מלא
                </span>
              </div>

              <div className="verification-warning-box">
                מוצגות מודעות מועמדות. ייתכן שחלקן לא עומדות בכל
                הפילטרים שנבחרו.
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}

export default ResultsHeader;