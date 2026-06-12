// === Sales by Hour ===
function SalesByHour() {
  const [from, setFrom] = useState("2026-04-23");
  const [to, setTo] = useState("2026-04-30");
  const [branch, setBranch] = useState("MDL_11");
  const [hour, setHour] = useState("all");

  const rows = useMemo(() => AQ.buildHourlySales(branch, 8), [branch]);
  const byHour = useMemo(() => {
    const arr = Array(24).fill(0);
    rows.forEach(r => { arr[r.hour] += r.sum; });
    return arr;
  }, [rows]);

  const total = rows.reduce((s, r) => s + r.sum, 0);
  const peakHour = byHour.indexOf(Math.max(...byHour));
  const { sorted, sort, onSort } = useSortable(rows, "date", "desc");

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">
          <h1>Продажи по часам</h1>
          <span className="sub">Найдено записей: <b style={{ color: "var(--text)" }}>{rows.length}</b> · Пиковый час: <b style={{ color: "var(--text)" }}>{peakHour}:00</b> · Сумма: <b style={{ color: "var(--text)" }}>{AQ.fmtKZT(total)}</b></span>
        </div>
        <div className="page__actions">
          <button className="btn"><Icon name="download" size={14} /> Экспорт</button>
          <button className="btn btn--primary"><Icon name="refresh" size={14} /> Загрузить</button>
        </div>
      </div>

      <div className="filters">
        <div className="field">
          <label className="field-label">Дата начала</label>
          <input type="date" className="input" value={from} onChange={e => setFrom(e.target.value)} />
        </div>
        <div className="field">
          <label className="field-label">Дата окончания</label>
          <input type="date" className="input" value={to} onChange={e => setTo(e.target.value)} />
        </div>
        <div className="field">
          <label className="field-label">Подразделение</label>
          <select className="select" value={branch} onChange={e => setBranch(e.target.value)}>
            {AQ.BRANCHES.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        </div>
        <div className="field">
          <label className="field-label">Час</label>
          <select className="select" value={hour} onChange={e => setHour(e.target.value)}>
            <option value="all">Все</option>
            {Array.from({ length: 24 }).map((_, h) => <option key={h} value={h}>{h}:00</option>)}
          </select>
        </div>
      </div>

      <div className="kpi-row" style={{ marginBottom: 16 }}>
        <div className="kpi">
          <div className="kpi__label">Всего за период</div>
          <div className="kpi__value">{AQ.fmtKZT(total)}</div>
          <div className="kpi__foot"><span className="trend trend--pos"><Icon name="arrowUp" size={11} /> +8.4%</span><span style={{ fontSize: 11 }}>vs прошлая неделя</span></div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Пиковый час</div>
          <div className="kpi__value">{peakHour}:00<span className="unit">— {peakHour + 1}:00</span></div>
          <div className="kpi__foot"><span style={{ fontSize: 11, color: "var(--text-muted)" }}>{AQ.fmtKZT(byHour[peakHour])}</span></div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Среднее за час</div>
          <div className="kpi__value">{AQ.fmtKZT(total / Math.max(1, rows.length))}</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Активных часов в день</div>
          <div className="kpi__value">{Math.round(rows.length / 8)}<span className="unit">из 24</span></div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card__header">
          <div>
            <div className="card__title">Распределение продаж по часам</div>
            <div className="card__sub">Среднее за период · {AQ.BRANCHES.find(b => b.id === branch)?.name}</div>
          </div>
          <div className="seg">
            <button className="active">Сумма</button>
            <button>Чеки</button>
            <button>Ср. чек</button>
          </div>
        </div>
        <div style={{ padding: "10px 14px 14px" }}>
          <Bars data={byHour.map(v => v / 8)} labels={Array.from({ length: 24 }).map((_, i) => `${i}:00`)} height={300} />
        </div>
      </div>

      <div className="table-wrap">
        <div className="table-toolbar">
          <div className="search" style={{ width: 280 }}>
            <Icon name="search" size={13} style={{ color: "var(--text-subtle)" }} />
            <input placeholder="Поиск по часам…" />
          </div>
          <div className="spacer" />
          <button className="btn btn--ghost btn--sm"><Icon name="settings" size={13} /> Колонки</button>
        </div>
        <div className="table-scroll" style={{ maxHeight: 420 }}>
          <table className="tbl">
            <thead>
              <tr>
                <ThSort k="id" sort={sort} onSort={onSort}>ID</ThSort>
                <ThSort k="branch" sort={sort} onSort={onSort}>Подразделение</ThSort>
                <ThSort k="date" sort={sort} onSort={onSort}>Дата</ThSort>
                <ThSort k="hour" sort={sort} onSort={onSort} align="right">Час</ThSort>
                <ThSort k="sum" sort={sort} onSort={onSort} align="right">Сумма продаж</ThSort>
                <th>Создано</th>
              </tr>
            </thead>
            <tbody>
              {sorted.slice(0, 30).map(r => (
                <tr key={r.id}>
                  <td className="code">#{r.id}</td>
                  <td>{r.branch}</td>
                  <td className="muted">{AQ.fmtDate(r.date)}</td>
                  <td className="num mono">{r.hour}:00</td>
                  <td className="num"><b>{AQ.fmtKZT(r.sum)}</b></td>
                  <td className="muted code">{AQ.fmtDate(r.created)}, {String(r.hour).padStart(2,"0")}:05:00</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

window.SalesByHour = SalesByHour;
