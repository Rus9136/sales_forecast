// === Employees ===
function Employees() {
  const [role, setRole] = useState("all");
  const [status, setStatus] = useState("active");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState(new Set());
  const PER = 20;

  const filtered = useMemo(() => AQ.EMPLOYEES.filter(e =>
    (role === "all" || e.role === role) &&
    (status === "all" || (status === "active" ? e.active : !e.active)) &&
    (!q || e.fullName.toLowerCase().includes(q.toLowerCase()) || e.sysName.toLowerCase().includes(q.toLowerCase()) || (e.email && e.email.includes(q)))
  ), [role, status, q]);
  const { sorted, sort, onSort } = useSortable(filtered, "code", "asc");
  const pages = Math.max(1, Math.ceil(sorted.length / PER));
  const visible = sorted.slice((page - 1) * PER, page * PER);

  const toggle = (id) => {
    const s = new Set(selected);
    s.has(id) ? s.delete(id) : s.add(id);
    setSelected(s);
  };
  const allSel = visible.length > 0 && visible.every(r => selected.has(r.code));
  const someSel = visible.some(r => selected.has(r.code));
  const toggleAll = () => {
    const s = new Set(selected);
    if (allSel) visible.forEach(r => s.delete(r.code));
    else visible.forEach(r => s.add(r.code));
    setSelected(s);
  };

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">
          <h1>Сотрудники</h1>
          <span className="sub">Найдено: <b style={{ color: "var(--text)" }}>{AQ.fmtNum(filtered.length)}</b> из 1 639 · {AQ.EMPLOYEES.filter(e => e.active).length} активных</span>
        </div>
        <div className="page__actions">
          <button className="btn"><Icon name="upload" size={14} /> Импорт</button>
          <button className="btn"><Icon name="download" size={14} /> Экспорт</button>
          <button className="btn btn--primary"><Icon name="refresh" size={14} /> Обновить справочник</button>
        </div>
      </div>

      <div className="filters">
        <div className="field">
          <label className="field-label">Должность</label>
          <select className="select" value={role} onChange={e => setRole(e.target.value)}>
            <option value="all">Все должности</option>
            {AQ.ROLES.map(r => <option key={r}>{r}</option>)}
          </select>
        </div>
        <div className="field">
          <label className="field-label">Статус</label>
          <select className="select" value={status} onChange={e => setStatus(e.target.value)}>
            <option value="active">Только активные</option>
            <option value="inactive">Неактивные</option>
            <option value="all">Все</option>
          </select>
        </div>
        <div className="field" style={{ gridColumn: "span 2" }}>
          <label className="field-label">Поиск</label>
          <div className="search">
            <Icon name="search" size={14} style={{ color: "var(--text-subtle)" }} />
            <input placeholder="Поиск по имени, коду, логину, email…" value={q} onChange={e => setQ(e.target.value)} />
          </div>
        </div>
      </div>

      <div className="table-wrap">
        <div className="table-toolbar">
          {selected.size > 0 ? (
            <>
              <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Выбрано: <b style={{ color: "var(--text)" }}>{selected.size}</b></span>
              <button className="btn btn--sm"><Icon name="tag" size={12} /> Назначить роль</button>
              <button className="btn btn--sm"><Icon name="building" size={12} /> Перевести в филиал</button>
              <button className="btn btn--sm btn--danger">Деактивировать</button>
              <button className="btn btn--sm btn--ghost" onClick={() => setSelected(new Set())}>Снять</button>
            </>
          ) : (
            <>
              <span style={{ fontSize: 13, color: "var(--text-muted)" }}>1 639 сотрудников · 220 ролей</span>
            </>
          )}
          <div className="spacer" />
          <button className="btn btn--ghost btn--sm"><Icon name="settings" size={13} /> Колонки</button>
        </div>
        <div className="table-scroll" style={{ maxHeight: 600 }}>
          <table className="tbl">
            <thead>
              <tr>
                <th className="checkbox-cell stick-l"><Checkbox checked={allSel} indeterminate={!allSel && someSel} onChange={toggleAll} /></th>
                <ThSort k="code" sort={sort} onSort={onSort}>Код</ThSort>
                <ThSort k="sysName" sort={sort} onSort={onSort} sticky>Имя в системе</ThSort>
                <ThSort k="fullName" sort={sort} onSort={onSort}>ФИО</ThSort>
                <ThSort k="role" sort={sort} onSort={onSort}>Должность</ThSort>
                <th>Подразделения</th>
                <ThSort k="login" sort={sort} onSort={onSort}>Логин</ThSort>
                <th>Email</th>
                <th>Телефон</th>
                <ThSort k="hired" sort={sort} onSort={onSort}>Принят</ThSort>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {visible.map(e => (
                <tr key={e.code} className={selected.has(e.code) ? "selected" : ""}>
                  <td className="checkbox-cell stick-l"><Checkbox checked={selected.has(e.code)} onChange={() => toggle(e.code)} /></td>
                  <td className="code">{e.code}</td>
                  <td className="stick-l">
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span className="avatar" style={{ width: 24, height: 24, fontSize: 10 }}>{e.fullName.split(" ").map(p => p[0]).slice(0,2).join("")}</span>
                      <b style={{ fontWeight: 500 }}>{e.sysName}</b>
                    </div>
                  </td>
                  <td className="muted">{e.fullName}</td>
                  <td><span className="badge">{e.role}</span></td>
                  <td>
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                      {e.branches.slice(0, 2).map(bid => {
                        const b = AQ.BRANCHES.find(x => x.id === bid);
                        return <span key={bid} className="chip" style={{ height: 20, fontSize: 11 }}>{b?.name.slice(0, 14)}</span>;
                      })}
                    </div>
                  </td>
                  <td className="mono muted">{e.login}</td>
                  <td className="muted">{e.email || <span style={{ color: "var(--text-subtle)" }}>—</span>}</td>
                  <td className="muted code">{e.phone || <span style={{ color: "var(--text-subtle)" }}>—</span>}</td>
                  <td className="muted">{AQ.fmtDate(e.hired)}</td>
                  <td>
                    <span className={"badge " + (e.active ? "badge--pos" : "")}>
                      <span className={"dot " + (e.active ? "dot--pos" : "")}></span>
                      {e.active ? "Активен" : "Неактивен"}
                    </span>
                  </td>
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

window.Employees = Employees;
