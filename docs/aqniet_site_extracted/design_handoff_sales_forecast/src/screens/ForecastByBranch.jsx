// === Forecast by Branch ===
function ForecastByBranch() {
  const [period, setPeriod] = useState("apr");
  const rows = AQ.FORECAST;

  const totalPlan = rows.reduce((s, r) => s + r.plan, 0);
  const totalFact = rows.reduce((s, r) => s + r.fact, 0);
  const totalForecast = rows.reduce((s, r) => s + r.forecast, 0);

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">
          <h1>Прогноз по филиалам</h1>
          <span className="sub">Плановые показатели, фактическое выполнение и прогноз на конец периода</span>
        </div>
        <div className="page__actions">
          <div className="seg">
            <button className={period === "mar" ? "active" : ""} onClick={() => setPeriod("mar")}>Март 2026</button>
            <button className={period === "apr" ? "active" : ""} onClick={() => setPeriod("apr")}>Апрель 2026</button>
            <button className={period === "may" ? "active" : ""} onClick={() => setPeriod("may")}>Май 2026</button>
          </div>
          <button className="btn"><Icon name="download" size={14} /> Экспорт</button>
          <button className="btn btn--primary"><Icon name="refresh" size={14} /> Пересчитать</button>
        </div>
      </div>

      <div className="kpi-row" style={{ marginBottom: 16 }}>
        <div className="kpi">
          <div className="kpi__label">План на период</div>
          <div className="kpi__value">{AQ.fmtKZT(totalPlan)}</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Факт на сегодня</div>
          <div className="kpi__value">{AQ.fmtKZT(totalFact)}</div>
          <div className="kpi__foot"><span className="trend trend--pos"><Icon name="arrowUp" size={11} />{AQ.fmtPct(((totalFact-totalPlan*0.7)/(totalPlan*0.7))*100)}</span><span style={{ fontSize: 11 }}>vs ожидание</span></div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Прогноз на конец</div>
          <div className="kpi__value">{AQ.fmtKZT(totalForecast)}</div>
          <div className="kpi__foot"><span className={"trend " + (totalForecast >= totalPlan ? "trend--pos" : "trend--neg")}><Icon name={totalForecast >= totalPlan ? "arrowUp" : "arrowDown"} size={11} />{AQ.fmtPct(((totalForecast-totalPlan)/totalPlan)*100)}</span><span style={{ fontSize: 11 }}>к плану</span></div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Филиалов в зоне риска</div>
          <div className="kpi__value">{rows.filter(r => r.forecast < r.plan * 0.95).length}<span className="unit">из {rows.length}</span></div>
          <div className="kpi__foot"><span style={{ fontSize: 11, color: "var(--text-muted)" }}>прогноз ниже 95% плана</span></div>
        </div>
      </div>

      <div className="card">
        <div className="card__header">
          <div>
            <div className="card__title">Прогноз по филиалам</div>
            <div className="card__sub">Сортировка по проценту выполнения</div>
          </div>
          <div className="seg">
            <button className="active">Все</button>
            <button>В зоне риска</button>
            <button>Перевыполнение</button>
          </div>
        </div>
        <div className="forecast-rows">
          {rows.sort((a, b) => b.progress - a.progress).map(r => {
            const status = r.forecast >= r.plan * 1.02 ? "pos" : r.forecast >= r.plan * 0.95 ? "warn" : "neg";
            const meterClass = status === "pos" ? "" : status === "warn" ? "under" : "over";
            return (
              <div key={r.branchId} className="fr-row">
                <div className="nm">
                  <b>{r.branch}</b>
                  <div className="sub">{r.city} · {r.manager}</div>
                </div>
                <div className="num"><div style={{ fontSize: 11, color: "var(--text-subtle)" }}>План</div><div className="mono">{AQ.fmtCompact(r.plan)} ₸</div></div>
                <div className="num"><div style={{ fontSize: 11, color: "var(--text-subtle)" }}>Факт</div><div className="mono"><b>{AQ.fmtCompact(r.fact)} ₸</b></div></div>
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, marginBottom: 4 }}>
                    <span style={{ color: "var(--text-subtle)" }}>Прогноз: <b style={{ color: "var(--text)" }} className="mono">{AQ.fmtCompact(r.forecast)} ₸</b></span>
                    <span className="mono" style={{ color: "var(--text-muted)" }}>{Math.round(r.progress * 100)}%</span>
                  </div>
                  <div className="meter">
                    <i className={meterClass} style={{ width: `${Math.min(110, r.progress * 100)}%` }} />
                  </div>
                </div>
                <div className="delta">
                  <span className={"badge " + (status === "pos" ? "badge--pos" : status === "warn" ? "badge--warn" : "badge--neg")}>
                    {AQ.fmtPct(r.delta * 100)}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

window.ForecastByBranch = ForecastByBranch;
