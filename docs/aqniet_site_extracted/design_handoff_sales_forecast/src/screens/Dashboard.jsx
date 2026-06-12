// === Dashboard ===
function Dashboard({ goto }) {
  const last30 = AQ.DAILY_SALES.filter(s => {
    const today = new Date(2026, 3, 30);
    const cutoff = new Date(today);
    cutoff.setDate(today.getDate() - 30);
    return s.date >= cutoff;
  });
  const prev30 = AQ.DAILY_SALES.filter(s => {
    const today = new Date(2026, 3, 30);
    const start = new Date(today); start.setDate(today.getDate() - 60);
    const end = new Date(today); end.setDate(today.getDate() - 30);
    return s.date >= start && s.date < end;
  });
  const sumLast = last30.reduce((s, x) => s + x.sum, 0);
  const sumPrev = prev30.reduce((s, x) => s + x.sum, 0);
  const checks = Math.round(sumLast / 12500);
  const checksPrev = Math.round(sumPrev / 12700);
  const avg = sumLast / Math.max(1, checks);
  const avgPrev = sumPrev / Math.max(1, checksPrev);

  const dayBuckets = useMemo(() => {
    const map = new Map();
    last30.forEach(s => {
      const k = AQ.fmtDate(s.date);
      map.set(k, (map.get(k) || 0) + s.sum);
    });
    const entries = Array.from(map.entries()).sort((a, b) => {
      const [da, ma, ya] = a[0].split(".").map(Number);
      const [db, mb, yb] = b[0].split(".").map(Number);
      return new Date(ya, ma - 1, da) - new Date(yb, mb - 1, db);
    });
    return entries;
  }, []);
  const trendLabels = dayBuckets.map(([k]) => k.slice(0, 5));
  const trendData = dayBuckets.map(([, v]) => v);

  const forecastByDay = trendData.map((v, i) => v * (0.95 + (i / trendData.length) * 0.12));

  const sparkLast = trendData.slice(-12);

  const topBranches = useMemo(() => {
    const m = new Map();
    last30.forEach(s => m.set(s.branch, (m.get(s.branch) || 0) + s.sum));
    return Array.from(m.entries()).sort((a, b) => b[1] - a[1]).slice(0, 6);
  }, []);
  const topMax = topBranches[0]?.[1] || 1;

  const topWaiters = AQ.WAITERS.slice(0, 6);
  const topWaiterMax = topWaiters[0]?.sum || 1;

  const heatMax = useMemo(() => Math.max(...AQ.HEATMAP.flat()), []);
  const heatColor = (v) => {
    const t = v / heatMax;
    return `oklch(${0.96 - t * 0.34} ${0.02 + t * 0.13} 162)`;
  };
  const dows = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"];

  const KPIS = [
    {
      label: "Выручка за 30 дней",
      value: AQ.fmtKZT(sumLast),
      delta: ((sumLast - sumPrev) / sumPrev) * 100,
      spark: sparkLast,
    },
    {
      label: "Средний чек",
      value: AQ.fmtKZT(avg),
      delta: ((avg - avgPrev) / avgPrev) * 100,
      spark: sparkLast.map(v => v / 105),
    },
    {
      label: "Количество чеков",
      value: AQ.fmtNum(checks),
      delta: ((checks - checksPrev) / checksPrev) * 100,
      spark: sparkLast.map(v => v / 12500),
    },
    {
      label: "Бонусный фонд",
      value: AQ.fmtKZT(sumLast * 0.018),
      delta: 4.6,
      spark: sparkLast.map(v => v * 0.018),
    },
  ];

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">
          <h1>Дашборд</h1>
          <span className="sub">Период: 31.03 — 30.04.2026 · Все подразделения</span>
        </div>
        <div className="page__actions">
          <div className="seg">
            <button>7 дней</button>
            <button className="active">30 дней</button>
            <button>90 дней</button>
            <button>Год</button>
          </div>
          <button className="btn"><Icon name="filter" size={14} /> Фильтры</button>
          <button className="btn"><Icon name="download" size={14} /> Экспорт</button>
          <button className="btn btn--primary"><Icon name="refresh" size={14} /> Обновить</button>
        </div>
      </div>

      <div className="dash">
        <div className="kpi-row">
          {KPIS.map((k, i) => (
            <div key={i} className="kpi">
              <div className="kpi__label">{k.label}</div>
              <div className="kpi__value">{k.value}</div>
              <div className="kpi__foot">
                <span className={"trend " + (k.delta >= 0 ? "trend--pos" : "trend--neg")}>
                  <Icon name={k.delta >= 0 ? "arrowUp" : "arrowDown"} size={11} />
                  {AQ.fmtPct(k.delta)}
                </span>
                <span style={{ fontSize: 11 }}>vs пред. период</span>
              </div>
              <div className="kpi__spark"><Sparkline data={k.spark} /></div>
            </div>
          ))}
        </div>

        <div className="dash-row-2">
          <div className="card">
            <div className="card__header">
              <div>
                <div className="card__title">Динамика продаж — факт и прогноз</div>
                <div className="card__sub">Сравнение с прогнозируемой моделью</div>
              </div>
              <div className="seg">
                <button className="active">День</button>
                <button>Неделя</button>
                <button>Месяц</button>
              </div>
            </div>
            <div style={{ padding: "10px 14px 14px" }}>
              <LineChart
                series={[
                  { name: "Факт", data: trendData, color: "var(--accent)", area: true },
                  { name: "Прогноз", data: forecastByDay, color: "var(--text-subtle)", dashed: true },
                ]}
                labels={trendLabels}
              />
            </div>
          </div>
          <div className="card">
            <div className="card__header">
              <div>
                <div className="card__title">Топ филиалов</div>
                <div className="card__sub">По выручке за 30 дней</div>
              </div>
              <button className="btn btn--ghost btn--sm" onClick={() => goto("forecast-branch")}>Все <Icon name="chevronRight" size={11} /></button>
            </div>
            <div className="top-list">
              {topBranches.map(([nm, val], i) => (
                <div key={nm} className="top-row">
                  <span className="rank">{String(i + 1).padStart(2, "0")}</span>
                  <span className="nm">{nm}</span>
                  <span className="bar"><i style={{ width: `${(val / topMax) * 100}%` }} /></span>
                  <span className="val">{AQ.fmtCompact(val)} ₸</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="dash-row-2">
          <div className="card">
            <div className="card__header">
              <div>
                <div className="card__title">Heatmap — продажи по часам и дням недели</div>
                <div className="card__sub">Пиковые периоды активности</div>
              </div>
              <div className="heatmap-legend">
                <span>меньше</span>
                <span className="scale">
                  {[0, 0.2, 0.4, 0.6, 0.8, 1].map((t, i) => (
                    <i key={i} style={{ background: `oklch(${0.96 - t * 0.34} ${0.02 + t * 0.13} 162)` }} />
                  ))}
                </span>
                <span>больше</span>
              </div>
            </div>
            <div style={{ padding: 16 }}>
              <div className="heatmap" style={{ marginBottom: 4 }}>
                <span></span>
                {Array.from({ length: 24 }).map((_, h) => (
                  <span key={h} className="h-col">{h % 3 === 0 ? `${h}` : ""}</span>
                ))}
              </div>
              {AQ.HEATMAP.map((row, di) => (
                <div key={di} className="heatmap" style={{ marginBottom: 3 }}>
                  <span className="h-row-label">{dows[di]}</span>
                  {row.map((v, h) => (
                    <div key={h} className="h-cell" style={{ background: heatColor(v) }} title={`${dows[di]} ${h}:00 — ${AQ.fmtKZT(v)}`} />
                  ))}
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <div className="card__header">
              <div>
                <div className="card__title">Топ официантов</div>
                <div className="card__sub">По выручке за период</div>
              </div>
              <button className="btn btn--ghost btn--sm" onClick={() => goto("sales-waiter")}>Все <Icon name="chevronRight" size={11} /></button>
            </div>
            <div className="top-list">
              {topWaiters.map((w, i) => (
                <div key={w.id} className="top-row">
                  <span className="rank">{String(i + 1).padStart(2, "0")}</span>
                  <span className="nm">
                    {w.name}
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{w.branch}</div>
                  </span>
                  <span className="bar"><i style={{ width: `${(w.sum / topWaiterMax) * 100}%` }} /></span>
                  <span className="val">{AQ.fmtCompact(w.sum)} ₸</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

window.Dashboard = Dashboard;
