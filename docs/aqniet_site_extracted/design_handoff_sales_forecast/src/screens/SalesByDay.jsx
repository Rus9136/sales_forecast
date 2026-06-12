// === Sales by Day ===
function SalesByDay() {
  const [from, setFrom] = useState("2026-03-31");
  const [to, setTo] = useState("2026-04-30");
  const [branch, setBranch] = useState("all");
  const [selected, setSelected] = useState(new Set());
  const [page, setPage] = useState(1);
  const PER = 14;

  const filtered = useMemo(() => {
    const fd = new Date(from); const td = new Date(to);
    return AQ.DAILY_SALES.filter(s =>
      s.date >= fd && s.date <= td &&
      (branch === "all" || s.branchId === branch)
    );
  }, [from, to, branch]);

  const { sorted, sort, onSort } = useSortable(filtered, "date", "desc");
  const pages = Math.max(1, Math.ceil(sorted.length / PER));
  const visible = sorted.slice((page - 1) * PER, page * PER);

  const total = filtered.reduce((s, x) => s + x.sum, 0);
  const totalChecks = filtered.length * 80;

  const toggle = (id) => {
    const s = new Set(selected);
    s.has(id) ? s.delete(id) : s.add(id);
    setSelected(s);
  };
  const allSel = visible.every(r => selected.has(r.id));
  const someSel = visible.some(r => selected.has(r.id));
  const toggleAll = () => {
    const s = new Set(selected);
    if (allSel) visible.forEach(r => s.delete(r.id));
    else visible.forEach(r => s.add(r.id));
    setSelected(s);
  };

  // Daily aggregate for chart
  const byDay = useMemo(() => {
    const m = new Map();
    filtered.forEach(s => {
      const k = AQ.fmtDate(s.date);
      m.set(k, (m.get(k) || 0) + s.sum);
    });
    return Array.from(m.entries()).sort((a, b) => {
      const [da, ma, ya] = a[0].split(".").map(Number);
      const [db, mb, yb] = b[0].split(".").map(Number);
      return new Date(ya, ma - 1, da) - new Date(yb, mb - 1, db);
    });
  }, [filtered]);

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">
          <h1>Продажи по дням</h1>
          <span className="sub">Найдено записей: <b style={{ color: "var(--text)" }}>{AQ.fmtNum(filtered.length)}</b> · Сумма: <b style={{ color: "var(--text)" }}>{AQ.fmtKZT(total)}</b></span>
        </div>
        <div className="page__actions">
          <button className="btn"><Icon name="upRight" size={13} /> Сохранить вид</button>
          <button className="btn"><Icon name="download" size={14} /> Экспорт CSV</button>
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
            <option value="all">Все подразделения</option>
            {AQ.BRANCHES.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        </div>
        <div className="actions">
          <button className="btn btn--primary"><Icon name="refresh" size={14} /> Загрузить</button>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card__header">
          <div>
            <div className="card__title">Динамика по дням</div>
            <div className="card__sub">{byDay.length} дней · среднее {AQ.fmtKZT(total / Math.max(1, byDay.length))}</div>
          </div>
        </div>
        <div style={{ padding: "10px 14px 14px" }}>
          <Bars data={byDay.map(d => d[1])} labels={byDay.map(d => d[0].slice(0, 5))} height={260} />
        </div>
      </div>

      <div className="table-wrap">
        <div className="table-toolbar">
          {selected.size > 0 ? (
            <>
              <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Выбрано: <b style={{ color: "var(--text)" }}>{selected.size}</b></span>
              <button className="btn btn--sm"><Icon name="download" size={12} /> Экспорт</button>
              <button className="btn btn--sm btn--danger"><Icon name="close" size={12} /> Очистить</button>
              <button className="btn btn--sm btn--ghost" onClick={() => setSelected(new Set())}>Снять</button>
            </>
          ) : (
            <>
              <div className="search" style={{ width: 260 }}>
                <Icon name="search" size={13} style={{ color: "var(--text-subtle)" }} />
                <input placeholder="Поиск по подразделению…" />
              </div>
              <span className="chip">Период: {from} — {to} <span className="chip__close"><Icon name="close" size={10} /></span></span>
              {branch !== "all" && <span className="chip">{AQ.BRANCHES.find(b => b.id === branch)?.name} <span className="chip__close" onClick={() => setBranch("all")}><Icon name="close" size={10} /></span></span>}
            </>
          )}
          <div className="spacer" />
          <button className="btn btn--ghost btn--sm"><Icon name="filter" size={13} /> Фильтры</button>
          <button className="btn btn--ghost btn--sm"><Icon name="settings" size={13} /> Колонки</button>
        </div>
        <div className="table-scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th className="checkbox-cell stick-l"><Checkbox checked={allSel} indeterminate={!allSel && someSel} onChange={toggleAll} /></th>
                <ThSort k="id" sort={sort} onSort={onSort}>ID</ThSort>
                <ThSort k="branch" sort={sort} onSort={onSort}>Подразделение</ThSort>
                <ThSort k="date" sort={sort} onSort={onSort}>Дата</ThSort>
                <ThSort k="sum" sort={sort} onSort={onSort} align="right">Сумма продаж</ThSort>
                <th>Создано</th>
                <th>Синхронизировано</th>
                <th style={{ width: 40 }}></th>
              </tr>
            </thead>
            <tbody>
              {visible.map(r => (
                <tr key={r.id} className={selected.has(r.id) ? "selected" : ""}>
                  <td className="checkbox-cell stick-l"><Checkbox checked={selected.has(r.id)} onChange={() => toggle(r.id)} /></td>
                  <td className="code">#{r.id}</td>
                  <td><b style={{ fontWeight: 500 }}>{r.branch}</b></td>
                  <td className="muted">{AQ.fmtDate(r.date)}</td>
                  <td className="num"><b>{AQ.fmtKZT(r.sum)}</b></td>
                  <td className="muted code">{AQ.fmtDate(r.created)}, 02:00:02</td>
                  <td className="muted code">{AQ.fmtDate(r.synced)}, 02:00:02</td>
                  <td><button className="btn btn--ghost btn--icon btn--sm"><Icon name="more" size={12} /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="table-footer">
          <span>Показано {(page - 1) * PER + 1}–{Math.min(page * PER, sorted.length)} из {AQ.fmtNum(sorted.length)}</span>
          <div className="spacer" />
          <Pager page={page} pages={pages} onPage={setPage} />
        </div>
      </div>
    </div>
  );
}

window.SalesByDay = SalesByDay;
