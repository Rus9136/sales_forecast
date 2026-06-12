// === Fact vs Forecast ===
function FactVsForecast() {
  const today = new Date(2026, 3, 30);
  const labels = [];
  const fact = [];
  const forecast = [];
  for (let i = 29; i >= 0; i--) {
    const d = new Date(today); d.setDate(today.getDate() - i);
    labels.push(AQ.fmtDate(d).slice(0, 5));
    const v = AQ.DAILY_SALES.filter(s => +s.date === +d).reduce((a, b) => a + b.sum, 0);
    fact.push(v);
    forecast.push(v * (0.94 + ((30 - i) / 30) * 0.14));
  }

  const totalFact = fact.reduce((a, b) => a + b, 0);
  const totalForecast = forecast.reduce((a, b) => a + b, 0);
  const dev = ((totalFact - totalForecast) / totalForecast) * 100;

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">
          <h1>Сравнение факт / прогноз</h1>
          <span className="sub">Точность модели прогнозирования за выбранный период</span>
        </div>
        <div className="page__actions">
          <button className="btn"><Icon name="download" size={14} /> Экспорт</button>
        </div>
      </div>

      <div className="kpi-row" style={{ marginBottom: 16 }}>
        <div className="kpi">
          <div className="kpi__label">Факт</div>
          <div className="kpi__value">{AQ.fmtKZT(totalFact)}</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Прогноз</div>
          <div className="kpi__value">{AQ.fmtKZT(totalForecast)}</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Отклонение</div>
          <div className="kpi__value">{AQ.fmtPct(dev)}</div>
          <div className="kpi__foot"><span className={"trend " + (dev >= 0 ? "trend--pos" : "trend--neg")}><Icon name={dev >= 0 ? "arrowUp" : "arrowDown"} size={11} />{AQ.fmtKZT(Math.abs(totalFact - totalForecast))}</span></div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Точность модели</div>
          <div className="kpi__value">{(100 - Math.abs(dev)).toFixed(1)}<span className="unit">%</span></div>
          <div className="kpi__foot"><span style={{ fontSize: 11, color: "var(--text-muted)" }}>MAPE по 30 дням</span></div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card__header">
          <div>
            <div className="card__title">Факт vs Прогноз — 30 дней</div>
            <div className="card__sub">Линия — прогноз, область — фактические продажи</div>
          </div>
          <div className="seg">
            <button>День</button>
            <button className="active">Линия</button>
            <button>Гэп</button>
          </div>
        </div>
        <div style={{ padding: "10px 14px 14px" }}>
          <LineChart
            height={340}
            series={[
              { name: "Факт", data: fact, color: "var(--accent)", area: true },
              { name: "Прогноз", data: forecast, color: "var(--text-subtle)", dashed: true },
            ]}
            labels={labels}
          />
        </div>
      </div>

      <div className="card">
        <div className="card__header">
          <div>
            <div className="card__title">Точность по филиалам</div>
            <div className="card__sub">Где модель ошибается больше всего</div>
          </div>
        </div>
        <div className="table-scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th>Филиал</th>
                <th>Город</th>
                <th style={{ textAlign: "right" }}>Факт</th>
                <th style={{ textAlign: "right" }}>Прогноз</th>
                <th style={{ textAlign: "right" }}>Отклонение</th>
                <th style={{ textAlign: "right" }}>Точность</th>
              </tr>
            </thead>
            <tbody>
              {AQ.FORECAST.map(r => {
                const d = ((r.fact - r.forecast * 0.7) / (r.forecast * 0.7)) * 100;
                const acc = 100 - Math.abs(d);
                return (
                  <tr key={r.branchId}>
                    <td><b style={{ fontWeight: 500 }}>{r.branch}</b></td>
                    <td className="muted">{r.city}</td>
                    <td className="num"><b>{AQ.fmtKZT(r.fact)}</b></td>
                    <td className="num muted">{AQ.fmtKZT(Math.round(r.forecast * 0.7))}</td>
                    <td className="num"><span className={"badge " + (Math.abs(d) <= 4 ? "badge--pos" : Math.abs(d) <= 10 ? "badge--warn" : "badge--neg")}>{AQ.fmtPct(d)}</span></td>
                    <td className="num mono">{acc.toFixed(1)}%</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

window.FactVsForecast = FactVsForecast;
