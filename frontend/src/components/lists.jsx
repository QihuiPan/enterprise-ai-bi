import { Activity } from "lucide-react";
import { money } from "../utils/format";

export function CustomerSegments({ segments }) {
  return (
    <div className="segment-list">
      {segments.map((segment, index) => (
        <div className="segment-row" key={segment.name}>
          <span className={`segment-rank rank-${index + 1}`}>{index + 1}</span>
          <div><strong>{segment.name}</strong><small>{segment.customers} customers · {segment.average_orders} avg orders</small></div>
          <b>{money.format(segment.total_revenue)}</b>
        </div>
      ))}
    </div>
  );
}

export function AnomalyList({ anomalies }) {
  return (
    <div className="anomaly-list">
      {anomalies.slice(0, 4).map((item) => (
        <div className="anomaly-row" key={item.order_id}>
          <span><Activity size={15} /></span>
          <div><strong>{item.order_id}</strong><small>{item.region} · {item.category}</small></div>
          <b>{money.format(item.revenue)}</b>
        </div>
      ))}
    </div>
  );
}
