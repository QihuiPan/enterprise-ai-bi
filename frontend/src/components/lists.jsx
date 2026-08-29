import { Activity } from "lucide-react";
import { formatCurrency } from "../utils/format";

export function CustomerSegments({ segments, currency, entityLabel, frequencyLabel }) {
  return (
    <div className="segment-list">
      {segments.map((segment, index) => (
        <div className="segment-row" key={segment.name}>
          <span className={`segment-rank rank-${index + 1}`}>{index + 1}</span>
          <div>
            <strong>{segment.name}</strong>
            <small>
              {segment.customers} {entityLabel.toLowerCase()} · {segment.average_orders} {frequencyLabel.toLowerCase()}
            </small>
          </div>
          <b>{formatCurrency(segment.total_revenue, currency)}</b>
        </div>
      ))}
    </div>
  );
}

export function AnomalyList({ anomalies, currency }) {
  return (
    <div className="anomaly-list">
      {anomalies.slice(0, 4).map((item) => (
        <div className="anomaly-row" key={item.order_id}>
          <span><Activity size={15} /></span>
          <div><strong>{item.order_id}</strong><small>{item.region} · {item.category}</small></div>
          <b>{formatCurrency(item.revenue, currency)}</b>
        </div>
      ))}
    </div>
  );
}
