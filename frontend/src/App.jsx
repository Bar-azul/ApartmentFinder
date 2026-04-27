import { useRef, useState } from "react";
import axios from "axios";
import "./App.css";

import FeatureLegend from "./components/FeatureLegend";
import ResultsHeader from "./components/ResultsHeader";
import ApartmentCard from "./components/ApartmentCard";
import ApartmentModal from "./components/ApartmentModal";

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

const VERIFY_POLL_INTERVAL_MS = 1200;

function getYad2Url(apartment) {
  if (apartment?.yad2_url) return apartment.yad2_url;

  if (apartment?.token) {
    return `https://www.yad2.co.il/realestate/item/${apartment.token}`;
  }

  return "https://www.yad2.co.il/realestate/rent";
}

function App() {
  const [prompt, setPrompt] = useState("");
  const [selectedMustHave, setSelectedMustHave] = useState([]);
  const [apartments, setApartments] = useState([]);
  const [filters, setFilters] = useState(null);
  const [showFilters, setShowFilters] = useState(false);
  const [selectedApartment, setSelectedApartment] = useState(null);
  const [expandedImage, setExpandedImage] = useState(null);
  const [loading, setLoading] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [verificationStats, setVerificationStats] = useState(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");

  const searchRunIdRef = useRef(0);
  const searchPollRef = useRef(null);
  const verifyPollRef = useRef(null);

  const isPromptEmpty = !prompt.trim();

  function clearTimers() {
    if (searchPollRef.current) {
      clearInterval(searchPollRef.current);
      searchPollRef.current = null;
    }

    if (verifyPollRef.current) {
      clearInterval(verifyPollRef.current);
      verifyPollRef.current = null;
    }
  }

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

  async function startVerificationJob(apartmentsToVerify, requiredFeatures, runId) {
    setApartments([]);
    setVerifying(true);

    setVerificationStats({
      total: apartmentsToVerify.length,
      checked: 0,
      verified: 0,
      rejected: 0,
      failed: 0,
      done: false,
      fallback_mode: false,
    });

    try {
      const response = await axios.post(`${API_BASE_URL}/api/search/verify/start`, {
        apartments: apartmentsToVerify,
        required_features: requiredFeatures || [],
      });

      const verifyJobId = response.data.job_id;

      verifyPollRef.current = setInterval(async () => {
        try {
          if (runId !== searchRunIdRef.current) {
            clearTimers();
            return;
          }

          const progressResponse = await axios.get(
            `${API_BASE_URL}/api/search/verify/progress/${verifyJobId}`
          );

          const job = progressResponse.data;

          setApartments(job.verified_apartments || job.candidate_apartments || []);

          setVerificationStats({
            total: job.total || 0,
            checked: job.checked || 0,
            verified: job.verified || 0,
            rejected: job.rejected || 0,
            failed: job.failed || 0,
            done: !!job.done,
            fallback_mode: !!job.fallback_mode,
            fallback_message: job.fallback_message || null,
            status: job.status,
          });

          if (job.done) {
            clearInterval(verifyPollRef.current);
            verifyPollRef.current = null;
            setVerifying(false);
          }
        } catch (err) {
          clearInterval(verifyPollRef.current);
          verifyPollRef.current = null;
          setVerifying(false);
          setError("שגיאה באימות המודעות");
        }
      }, VERIFY_POLL_INTERVAL_MS);
    } catch (err) {
      setVerifying(false);
      setError(err.response?.data?.detail || "שגיאה בהתחלת אימות המודעות");
    }
  }

  async function handleSearch() {
    if (isPromptEmpty) {
      setError("צריך לכתוב פרומפט לפני שמחפשים");
      return;
    }

    clearTimers();

    searchRunIdRef.current += 1;
    const currentRunId = searchRunIdRef.current;

    setLoading(true);
    setVerifying(false);
    setProgress(0);
    setError("");
    setApartments([]);
    setFilters(null);
    setVerificationStats(null);
    setShowFilters(false);
    setSelectedApartment(null);
    setExpandedImage(null);

    try {
      const startResponse = await axios.post(`${API_BASE_URL}/api/search/start`, {
        prompt: prompt.trim(),
        must_have: selectedMustHave,
      });

      const jobId = startResponse.data.job_id;

      searchPollRef.current = setInterval(async () => {
        try {
          const progressResponse = await axios.get(
            `${API_BASE_URL}/api/search/progress/${jobId}`
          );

          const job = progressResponse.data;
          setProgress(job.progress || 0);

          if (job.done) {
            clearInterval(searchPollRef.current);
            searchPollRef.current = null;

            if (currentRunId !== searchRunIdRef.current) return;

            if (job.success && job.result) {
              const resultFilters = job.result.filters || null;
              const rawApartments = job.result.apartments || [];
              const requiredFeatures = resultFilters?.must_have || selectedMustHave || [];

              setFilters(resultFilters);
              setProgress(100);

              await startVerificationJob(rawApartments, requiredFeatures, currentRunId);
            } else {
              setError(job.error || "שגיאה בחיפוש");
            }

            setTimeout(() => {
              setLoading(false);
              setProgress(0);
            }, 700);
          }
        } catch (err) {
          clearTimers();
          setError(err.message || "שגיאה בבדיקת התקדמות");
          setLoading(false);
          setProgress(0);
        }
      }, 800);
    } catch (err) {
      clearTimers();
      setError(err.response?.data?.detail || err.message || "שגיאה בהתחלת החיפוש");
      setLoading(false);
      setProgress(0);
    }
  }

  function handleOpenApartment(apartment) {
    setSelectedApartment(apartment);
  }

  function handleOpenInYad2(apartment) {
    window.open(getYad2Url(apartment), "_blank", "noopener,noreferrer");
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
          placeholder="לדוגמה: חפש לי דירה בראשון לציון עם מרפסת מ-4000 עד 5500 שקל, בין 2.5 ל-4 חדרים"
        />

        <button onClick={handleSearch} disabled={loading || verifying || isPromptEmpty}>
          {loading ? "מחפש..." : verifying ? "מאמת מודעות..." : "חפש דירות"}
        </button>
      </section>

      {loading && <SearchProgress progress={progress} />}

      <FeatureLegend
        selectedMustHave={selectedMustHave}
        onToggle={toggleMustHave}
        onClear={clearMustHave}
      />

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

      <ResultsHeader
        apartmentsCount={apartments.length}
        verificationStats={verificationStats}
        isSearching={verifying}
        loading={loading}
      />

      {verifying && apartments.length === 0 && (
        <div className="verification-wait-box">
          <strong>בודק מודעות ברקע...</strong>
          <p>הכרטיסים יוצגו כאן רק אחרי שהמערכת תסיים לאמת אותם.</p>
        </div>
      )}

      <section className="grid">
        {apartments.map((apartment) => (
          <ApartmentCard
            key={`${apartment.order_id}-${apartment.token}`}
            apartment={apartment}
            onOpen={() => handleOpenApartment(apartment)}
            onOpenBrowser={() => handleOpenInYad2(apartment)}
          />
        ))}
      </section>

      {selectedApartment && (
        <ApartmentModal
          apartment={selectedApartment}
          onClose={() => setSelectedApartment(null)}
          onImageClick={setExpandedImage}
          onOpenBrowser={() => handleOpenInYad2(selectedApartment)}
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

export default App;