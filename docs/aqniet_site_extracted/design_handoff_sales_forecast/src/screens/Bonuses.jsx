// === Bonuses ===
function Bonuses() {
  const [tab, setTab] = useState("calc");
  const rows = AQ.BONUS_CALCS;
  const { sorted, sort, onSort } = useSortable(rows, "bonus", "desc");
  const totalBonus = rows.reduce((s, r) => s + r.bonus, 0);
  const totalBase = rows.reduce((s, r) => s + r.base, 0);
  const approved = rows.filter(r => r.status === "Согласован" || r.status === "Выплачен").length;

  const STATUS_BADGE = {
    "Согласован": "badge--pos",
    "На проверке": "badge--warn",
    "Черновик": "",
    "Выплачен": "badge--accent",
  };

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__title">
          <h1>Бонусы</h1>
          <span className="sub">Расчёты, схемы и помесячные планы</span>
        </div>
        <div className="page__actions">
          <button className="btn"><Icon name="download" size={14} /> Экспорт</button>
          <button className="btn btn--primary"><Icon name="plus" size={14} /> Новый расчёт</button>
        </div>
      </div>

      <div className="tabs">
        <button className={"tab " + (tab === "calc" ? "active" : "")} onClick={() => setTab("calc")}>Расчёты бонусов</button>
        <button className={"tab " + (tab === "scheme" ? "active" : "")} onClick={() => setTab("scheme")}>Схемы расчёта</button>
        <button className={"tab " + (tab === "kpi" ? "active" : "")} onClick={() => setTab("kpi")}>Ручной ввод KPI</button>
        <button className={"tab " + (tab === "plan" ? "active" : "")} onClick={() => setTab("plan")}>Помесячные планы</button>
      </div>

      {tab === "calc" && (
        <>
          <div className="bonus-summary" style={{ marginBottom: 16 }}>
            <div className="kpi">
              <div className="kpi__label">К начислению</div>
              <div className="kpi__value">{AQ.fmtKZT(totalBonus)}</div>
              <div className="kpi__foot"><span style={{ fontSize: 11, color: "var(--text-muted)" }}>{rows.length} расчётов</span></div>
            </div>
            <div className="kpi">
              <div className="kpi__label">База расчёта</div>
              <div className="kpi__value">{AQ.fmtKZT(totalBase)}</div>
            </div>
            <div className="kpi">
              <div className="kpi__label">Согласовано</div>
              <div className="kpi__value">{approved}<span className="unit">из {rows.length}</span></div>
              <div style={{ marginTop: 6 }} className="bonus-prog"><i style={{ width: `${(approved / rows.length) * 100}%` }} /></div>
            </div>
            <div className="kpi">
              <div className="kpi__label">К выплате 5 мая</div>
              <div className="kpi__value">{AQ.fmtKZT(rows.filter(r => r.status === "Согласован").reduce((s, r) => s + r.bonus, 0))}</div>
            </div>
          </div>

          <div className="table-wrap">
            <div className="table-toolbar">
              <div className="search" style={{ width: 280 }}>
                <Icon name="search" size={13} style={{ color: "var(--text-subtle)" }} />
                <input placeholder="Сотрудник, филиал, схема…" />
              </div>
              <span className="chip">Период: Апрель 2026 <span className="chip__close"><Icon name="close" size={10} /></span></span>
              <div className="spacer" />
              <button className="btn btn--ghost btn--sm"><Icon name="filter" size={13} /> Фильтры</button>
            </div>
            <div className="table-scroll" style={{ maxHeight: 560 }}>
              <table className="tbl">
                <thead>
                  <tr>
                    <th className="checkbox-cell stick-l"><Checkbox /></th>
                    <ThSort k="period" sort={sort} onSort={onSort}>Период</ThSort>
                    <ThSort k="employee" sort={sort} onSort={onSort}>Сотрудник</ThSort>
                    <ThSort k="role" sort={sort} onSort={onSort}>Роль</ThSort>
                    <ThSort k="branch" sort={sort} onSort={onSort}>Филиал</ThSort>
                    <ThSort k="scheme" sort={sort} onSort={onSort}>Схема</ThSort>
                    <ThSort k="planFact" sort={sort} onSort={onSort} align="right">План/Факт</ThSort>
                    <ThSort k="base" sort={sort} onSort={onSort} align="right">База</ThSort>
                    <ThSort k="bonus" sort={sort} onSort={onSort} align="right">Бонус</ThSort>
                    <ThSort k="status" sort={sort} onSort={onSort}>Статус</ThSort>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map(r => (
                    <tr key={r.id}>
                      <td className="checkbox-cell stick-l"><Checkbox /></td>
                      <td className="muted">{r.period}</td>
                      <td><b style={{ fontWeight: 500 }}>{r.employee}</b></td>
                      <td className="muted">{r.role}</td>
                      <td className="muted">{r.branch}</td>
                      <td className="muted">{r.scheme}</td>
                      <td className="num">
                        <span className={"badge " + (r.planFact >= 1 ? "badge--pos" : "badge--warn")}>{Math.round(r.planFact * 100)}%</span>
                      </td>
                      <td className="num mono">{AQ.fmtKZT(r.base)}</td>
                      <td className="num"><b>{AQ.fmtKZT(r.bonus)}</b></td>
                      <td><span className={"badge " + STATUS_BADGE[r.status]}>{r.status}</span></td>
                      <td><button className="btn btn--ghost btn--icon btn--sm"><Icon name="more" size={12} /></button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {tab === "scheme" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 12 }}>
          {AQ.BONUS_SCHEMES.map(s => (
            <div key={s.id} className="card">
              <div className="card__header">
                <div>
                  <div className="card__title">{s.name}</div>
                  <div className="card__sub">{s.roles.join(", ")}</div>
                </div>
                <button className="btn btn--ghost btn--icon btn--sm"><Icon name="edit" size={13} /></button>
              </div>
              <div className="card__body">
                <div className="drawer__row" style={{ borderBottom: "1px solid var(--border-faint)", padding: "8px 0" }}>
                  <span className="lbl">База</span><span className="val">{s.base}</span>
                </div>
                <div className="drawer__row" style={{ padding: "8px 0" }}>
                  <span className="lbl">Ставка</span><span className="val"><b>{s.rate}</b></span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === "kpi" && <KpiManual />}
      {tab === "plan" && <MonthlyPlan />}
    </div>
  );
}

function KpiManual() {
  return (
    <div className="card">
      <div className="card__header">
        <div>
          <div className="card__title">Ручной ввод KPI</div>
          <div className="card__sub">Корректировка показателей вне системы продаж</div>
        </div>
        <button className="btn btn--primary btn--sm"><Icon name="check" size={12} /> Сохранить</button>
      </div>
      <div className="table-scroll">
        <table className="tbl">
          <thead><tr><th>Сотрудник</th><th>Филиал</th><th>KPI</th><th style={{textAlign:"right"}}>План</th><th style={{textAlign:"right"}}>Факт</th><th style={{textAlign:"right"}}>%</th><th>Комментарий</th></tr></thead>
          <tbody>
            {AQ.WAITERS.slice(0, 12).map(w => {
              const plan = 250000;
              const fact = Math.round(plan * (0.7 + Math.random() * 0.6));
              return (
                <tr key={w.id}>
                  <td><b style={{fontWeight:500}}>{w.name}</b></td>
                  <td className="muted">{w.branch}</td>
                  <td>Ср. чек</td>
                  <td className="num mono">{AQ.fmtKZT(plan)}</td>
                  <td className="num"><input className="input" defaultValue={fact} style={{ width: 120, textAlign: "right", height: 28 }} /></td>
                  <td className="num"><span className={"badge " + (fact >= plan ? "badge--pos" : "badge--warn")}>{Math.round((fact/plan)*100)}%</span></td>
                  <td><input className="input" placeholder="—" style={{ height: 28 }} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MonthlyPlan() {
  const months = ["Янв","Фев","Мар","Апр","Май","Июн","Июл","Авг","Сен","Окт","Ноя","Дек"];
  return (
    <div className="card">
      <div className="card__header">
        <div>
          <div className="card__title">Помесячные планы — 2026</div>
          <div className="card__sub">Целевые показатели выручки по филиалам</div>
        </div>
        <button className="btn btn--ghost btn--sm"><Icon name="upload" size={13} /> Импорт из Excel</button>
      </div>
      <div className="table-scroll">
        <table className="tbl">
          <thead>
            <tr>
              <th className="stick-l">Филиал</th>
              {months.map(m => <th key={m} style={{ textAlign: "right" }}>{m}</th>)}
              <th style={{ textAlign: "right" }}>Год</th>
            </tr>
          </thead>
          <tbody>
            {AQ.BRANCHES.map(b => {
              const base = 25_000_000 + Math.random() * 30_000_000;
              const vals = months.map((_, i) => Math.round(base * (0.9 + (i/11)*0.3) * (0.92 + Math.random()*0.16)));
              const total = vals.reduce((a,b)=>a+b,0);
              return (
                <tr key={b.id}>
                  <td className="stick-l"><b style={{fontWeight:500}}>{b.name}</b></td>
                  {vals.map((v, i) => (
                    <td key={i} className="num mono" style={{ color: i === 3 ? "var(--text)" : "var(--text-muted)" }}>
                      {AQ.fmtCompact(v)}
                    </td>
                  ))}
                  <td className="num"><b>{AQ.fmtCompact(total)} ₸</b></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

window.Bonuses = Bonuses;
