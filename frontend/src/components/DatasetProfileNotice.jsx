import { Database, Info } from "lucide-react";
import { number } from "../utils/format";

function importedLabel(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

export function DatasetProfileNotice({ profile }) {
  if (!profile) return null;
  const importedAt = importedLabel(profile.imported_at);
  const notes = [...new Set([
    profile.semantic_warning,
    profile.entity_warning,
    profile.unit_warning,
    ...(profile.warnings ?? []),
  ].filter(Boolean))];
  const sourceParts = [
    profile.original_filename,
    profile.source_sheet ? `Sheet: ${profile.source_sheet}` : null,
    profile.currency
      ? `Currency: ${profile.currency}${profile.currency_verified === false ? " (unverified fallback)" : ""}`
      : null,
    `${number.format(profile.rows_loaded ?? 0)} validated rows`,
    profile.date_min && profile.date_max ? `${profile.date_min} — ${profile.date_max}` : null,
  ].filter(Boolean);
  const provenanceParts = [
    importedAt ? `Imported ${importedAt}` : null,
    profile.content_sha256 ? `SHA-256 ${profile.content_sha256.slice(0, 12)}…` : null,
  ].filter(Boolean);

  return (
    <section className="dataset-profile-notice" aria-labelledby="active-dataset-title">
      <span className="dataset-profile-icon"><Database size={18} aria-hidden="true" /></span>
      <div className="dataset-profile-copy">
        <div className="dataset-profile-heading">
          <strong id="active-dataset-title">{profile.dataset_name}</strong>
          <span>{String(profile.source_format || "data").toUpperCase()}</span>
        </div>
        <p>{sourceParts.join(" · ")}</p>
        {provenanceParts.length > 0 && <small>{provenanceParts.join(" · ")}</small>}
      </div>
      {notes.length > 0 && (
        <details className="dataset-profile-notes">
          <summary><Info size={14} aria-hidden="true" />{notes.length} data {notes.length === 1 ? "note" : "notes"}</summary>
          <ul>{notes.map((note) => <li key={note}>{note}</li>)}</ul>
        </details>
      )}
    </section>
  );
}
