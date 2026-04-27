function SearchBox({
  prompt,
  setPrompt,
  loading,
  verifying,
  isPromptEmpty,
  onSearch,
}) {
  return (
    <section className="search-box">
      <textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="לדוגמה: חפש לי דירה בראשון לציון עם מרפסת מ-4000 עד 5500 שקל, בין 2.5 ל-4 חדרים"
      />

      <button onClick={onSearch} disabled={loading || verifying || isPromptEmpty}>
        {loading ? "מחפש..." : verifying ? "מאמת מודעות..." : "חפש דירות"}
      </button>
    </section>
  );
}

export default SearchBox;