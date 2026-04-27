function SearchProgress({ progress }) {
  return (
    <div className="search-progress">
      <div className="progress-header">
        <span>מחפש מודעות...</span>
        <strong>{progress}%</strong>
      </div>

      <div className="progress-track">
        <div className="progress-fill" style={{ width: `${progress}%` }} />
      </div>

      <div className="progress-steps">
        <span className={progress >= 15 ? "active" : ""}>Map API</span>
        <span className={progress >= 45 ? "active" : ""}>איסוף תוצאות</span>
        <span className={progress >= 75 ? "active" : ""}>הכנת כרטיסים</span>
        <span className={progress >= 100 ? "active" : ""}>סיום</span>
      </div>
    </div>
  );
}

export default SearchProgress;