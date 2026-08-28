import { useState } from "react";
import { Bot, Database, LoaderCircle, Send, Sparkles } from "lucide-react";

const DEFAULT_QUESTION = "Why did revenue change in the latest month?";

export function IntelligenceSection({ insight, busy, onAsk }) {
  const [question, setQuestion] = useState(DEFAULT_QUESTION);

  function submit(event) {
    event.preventDefault();
    const normalized = question.trim();
    if (normalized.length >= 5) onAsk(normalized);
  }

  return (
    <section className="intelligence" id="intelligence">
      <div className="intelligence-copy">
        <span className="eyebrow light">GROUNDED MULTI-AGENT SYSTEM</span>
        <h2>Ask the business.<br />Inspect the evidence.</h2>
        <p>Every answer lists the analytical tools and source metrics used. No generated SQL reaches the database.</p>
        <form onSubmit={submit} className="question-form">
          <input value={question} onChange={(event) => setQuestion(event.target.value)} aria-label="Business question" />
          <button disabled={busy} aria-label="Ask agents">{busy ? <LoaderCircle className="spin" /> : <Send />}</button>
        </form>
      </div>
      <div className="insight-card">
        <div className="insight-heading"><span><Bot size={18} /></span><div><strong>Executive Agent</strong><small>{insight ? insight.agents_used.join(" + ") : "Ready for a grounded question"}</small></div></div>
        {insight ? (
          <>
            <p className="insight-answer">{insight.answer}</p>
            <div className="evidence-block">
              <span>EVIDENCE TRAIL</span>
              {insight.evidence.slice(0, 3).map((item) => (
                <div key={`${item.source}-${item.metric}`}><Database size={13} /><b>{item.metric}</b><small>{item.source}</small></div>
              ))}
            </div>
          </>
        ) : (
          <div className="insight-placeholder"><Sparkles size={24} /><p>Try “Forecast the next quarter” or “Which customers create the most value?”</p></div>
        )}
      </div>
    </section>
  );
}
