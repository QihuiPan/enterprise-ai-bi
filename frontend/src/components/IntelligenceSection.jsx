import { useState } from "react";
import { Bot, Database, LoaderCircle, Send, Sparkles } from "lucide-react";
import { InsightVisualization } from "./charts";

const DEFAULT_QUESTION = "Why did revenue change in the latest month?";

function QueryPlanSummary({ plan, explanation }) {
  if (!plan && !explanation) return null;
  return (
    <div className="query-plan">
      <span>READ-ONLY QUERY PLAN</span>
      {plan && (
        <dl>
          <div><dt>Operation</dt><dd>{plan.operation}</dd></div>
          <div><dt>Metric</dt><dd>{plan.metric?.replaceAll("_", " ")}</dd></div>
          {plan.dimension && <div><dt>Dimension</dt><dd>{plan.dimension}</dd></div>}
          <div><dt>Period</dt><dd>{plan.period?.label ?? "Available data"}</dd></div>
          {plan.grain && <div><dt>Grain</dt><dd>{plan.grain}</dd></div>}
          {plan.limit && <div><dt>Limit</dt><dd>{plan.limit}</dd></div>}
          {plan.truncated && (
            <div>
              <dt>Coverage</dt>
              <dd>Showing {plan.result_count} of {plan.total_results ?? plan.total_points}</dd>
            </div>
          )}
        </dl>
      )}
      {explanation && <p>{explanation}</p>}
    </div>
  );
}

export function IntelligenceSection({ insight, busy, currency, onAsk }) {
  const [question, setQuestion] = useState(DEFAULT_QUESTION);

  function submit(event) {
    event.preventDefault();
    const normalized = question.trim();
    if (normalized) onAsk(normalized);
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
        <div className="insight-heading"><span><Bot size={18} /></span><div><strong>Agent response</strong><small>{insight ? insight.agents_used.join(" + ") : "Ready for a grounded question"}</small></div></div>
        {insight ? (
          <>
            <p className="insight-answer">{insight.answer}</p>
            <QueryPlanSummary plan={insight.query_plan} explanation={insight.explanation} />
            <InsightVisualization chart={insight.chart} currency={currency} />
            <div className="evidence-block">
              <span>EVIDENCE TRAIL</span>
              {insight.evidence.slice(0, 3).map((item) => (
                <div key={`${item.source}-${item.metric}`}><Database size={13} /><b>{item.metric}</b><small>{item.source}</small></div>
              ))}
            </div>
          </>
        ) : (
          <div className="insight-placeholder"><Sparkles size={24} /><p>Try “Forecast the next quarter” or “Top customers by revenue”</p></div>
        )}
      </div>
    </section>
  );
}
