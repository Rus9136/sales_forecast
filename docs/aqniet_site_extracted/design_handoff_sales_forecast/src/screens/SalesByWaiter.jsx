// === Sales by Waiter ===
function SalesByWaiter() {
  const [branch, setBranch] = useState("all");
  const [q, setQ] = useState("");
  const filtered = useMemo(() =>
    AQ.WAITERS.filter(w =>
      (branch === "all" || w.branchId === branch) &&
      (!q || w.name.toLowerCase().includes(q.toLowerCase()))
    ), [branch, q]);
  const { sorted, sort, onSort } = useSortable(filtered, "sum", "desc");
  const total = filtered.reduce((s, w) => s + w.sum, 0);
  const totalChecks = filtered.reduce((s, w) => s + w.checks, 0);
  const avg = total / Math.max(1, totalChecks);

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">
          <h1>Продажи по официантам</h1>
          <span className="sub">{filtered.length} сотрудников · {AQ.fmtNum(totalChecks)} чеков · средний {AQ.fmtKZT(avg)}</span>
        </div>
        <div className="page__actions">
          <button className="btn"><Icon name="download" size={14} /> Экспорт</button>
          <button className="btn btn--primary"><Icon name="upload" size={14} /> Загрузить из R-Keeper</button>
        </div>
      </div>

      <div className="filters">
        <div className="field">
          <label className="field-label">Период</label>
          <select className="select" defaultValue="m"><option value="d">Сегодня</option><option value="w">Эта неделя</option><option value="m">Апрель 2026</option><option value="q">I квартал</option></select>
        </div>
        <div className="field">
          <label className="field-label">Подразделение</label>
          <select className="select" value={branch} onChange={e => setBranch(e.target.value)}>
            <option value="all">Все подразделения</option>
            {AQ.BRANCHES.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        </div>
        <div className="field" style={{ gridColumn: "span 2" }}>
          <label className="field-label">Поиск</label>
          <div className="search">
            <Icon name="search" size={14} style={{ color: "var(--text-subtle)" }} />
            <input placeholder="Имя сотрудника…" value={q} onChange={e => setQ(e.target.value)} />
          </div>
        </div>
      </div>

      <div className="table-wrap">
        <div className="table-toolbar">
          <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Выручка по сотрудникам: <b style={{ color: "var(--text)" }}>{AQ.fmtKZT(total)}</b></span>
          <div className="spacer" />
          <div className="seg">
            <button className="active">Список</button>
            <button>Карточки</button>
          </div>
          <button className="btn btn--ghost btn--sm"><Icon name="filter" size={13} /> Фильтры</button>
        </div>
        <div className="table-scroll" style={{ maxHeight: 600 }}>
          <table className="tbl">
            <thead>
              <tr>
                <th className="checkbox-cell stick-l"><Checkbox /></th>
                <ThSort k="name" sort={sort} onSort={onSort} sticky>Сотрудник</ThSort>
                <ThSort k="branch" sort={sort} onSort={onSort}>Филиал</ThSort>
                <ThSort k="checks" sort={sort} onSort={onSort} align="right">Чеков</ThSort>
                <ThSort k="avgCheck" sort={sort} onSort={onSort} align="right">Средний чек</ThSort>
                <ThSort k="sum" sort={sort} onSort={onSort} align="right">Сумма продаж</ThSort>
                <ThSort k="tips" sort={sort} onSort={onSort} align="right">Чаевые</ThSort>
                <ThSort k="rating" sort={sort} onSort={onSort} align="right">Рейтинг</ThSort>
                <ThSort k="shifts" sort={sort} onSort={onSort} align="right">Смен</ThSort>
              </tr>
            </thead>
            <tbody>
              {sorted.map((w, i) => (
                <tr key={w.id}>
                  <td className="checkbox-cell stick-l"><Checkbox /></td>
                  <td className="stick-l">
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span className="avatar" style={{ width: 26, height: 26, fontSize: 11 }}>{w.name.split(" ").map(p => p[0]).slice(0,2).join("")}</span>
                      <div>
                        <div style={{ fontWeight: 500 }}>{w.name}</div>
                        <div style={{ fontSize: 11, color: "var(--text-muted)" }}>id #{w.id}</div>
                      </div>
                    </div>
                  </td>
                  <td className="muted">{w.branch}</td>
                  <td className="num mono">{AQ.fmtNum(w.checks)}</td>
                  <td className="num">{AQ.fmtKZT(w.avgCheck)}</td>
                  <td className="num"><b>{AQ.fmtKZT(w.sum)}</b></td>
                  <td className="num muted">{AQ.fmtKZT(w.tips)}</td>
                  <td className="num">
                    <span className={"badge " + (w.rating >= 4.7 ? "badge--pos" : w.rating >= 4.4 ? "badge--accent" : "")}>★ {w.rating.toFixed(2)}</span>
                  </td>
                  <td className="num mono muted">{w.shifts}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

window.SalesByWaiter = SalesByWaiter;
