// === Departments ===
function Departments() {
  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">
          <h1>Подразделения</h1>
          <span className="sub">Структура холдинга, филиалы и сети</span>
        </div>
        <div className="page__actions">
          <button className="btn"><Icon name="download" size={14} /> Экспорт</button>
          <button className="btn btn--primary"><Icon name="plus" size={14} /> Добавить</button>
        </div>
      </div>

      <div className="kpi-row" style={{ marginBottom: 16 }}>
        <div className="kpi">
          <div className="kpi__label">Сетей</div>
          <div className="kpi__value">4</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Филиалов</div>
          <div className="kpi__value">{AQ.BRANCHES.length}</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Городов</div>
          <div className="kpi__value">{new Set(AQ.BRANCHES.map(b => b.city)).size}</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Сотрудников</div>
          <div className="kpi__value">1 639</div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
        {["Madlen", "Tary", "Sandyq", "Kainar"].map(net => {
          const branches = AQ.BRANCHES.filter(b => b.name.toLowerCase().includes(net.toLowerCase()) || b.id.startsWith(net.slice(0,3).toUpperCase()));
          const total = branches.length;
          return (
            <div key={net} className="card">
              <div className="card__header">
                <div>
                  <div className="card__title">{net}</div>
                  <div className="card__sub">{total} филиалов</div>
                </div>
                <span className="badge badge--accent">Сеть</span>
              </div>
              <div>
                {branches.map(b => (
                  <div key={b.id} style={{ display: "grid", gridTemplateColumns: "1fr auto auto", gap: 12, padding: "10px 16px", borderBottom: "1px solid var(--border-faint)", alignItems: "center", fontSize: 13 }}>
                    <div>
                      <b style={{ fontWeight: 500 }}>{b.name}</b>
                      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{b.city} · управляющий: {b.manager}</div>
                    </div>
                    <span className="badge"><Icon name="users" size={11} /> {b.staff}</span>
                    <button className="btn btn--ghost btn--icon btn--sm"><Icon name="chevronRight" size={12} /></button>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      <div className="table-wrap">
        <div className="table-toolbar">
          <div className="search" style={{ width: 280 }}>
            <Icon name="search" size={13} style={{ color: "var(--text-subtle)" }} />
            <input placeholder="Поиск по филиалам…" />
          </div>
          <div className="spacer" />
        </div>
        <div className="table-scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th>Филиал</th>
                <th>Город</th>
                <th>Управляющий</th>
                <th style={{ textAlign: "right" }}>Сотрудников</th>
                <th style={{ textAlign: "right" }}>Выручка / мес</th>
                <th>Открыт</th>
              </tr>
            </thead>
            <tbody>
              {AQ.BRANCHES.map((b, i) => (
                <tr key={b.id}>
                  <td><b style={{ fontWeight: 500 }}>{b.name}</b><div style={{ fontSize: 11, color: "var(--text-muted)" }}>id {b.id}</div></td>
                  <td className="muted">{b.city}</td>
                  <td>{b.manager}</td>
                  <td className="num mono">{b.staff}</td>
                  <td className="num"><b>{AQ.fmtCompact(35_000_000 + i * 7_000_000)} ₸</b></td>
                  <td className="muted">2022 — 2025</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

window.Departments = Departments;
