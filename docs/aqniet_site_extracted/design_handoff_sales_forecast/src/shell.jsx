// === Shell: Sidebar + Topbar + CmdK palette ===

const NAV = [
  {
    title: "Аналитика",
    items: [
      { id: "dashboard", label: "Дашборд", icon: "dashboard" },
    ],
  },
  {
    title: "Продажи",
    items: [
      { id: "sales-day", label: "Продажи по дням", icon: "calendar" },
      { id: "sales-hour", label: "Продажи по часам", icon: "clock" },
      { id: "sales-waiter", label: "Продажи по официантам", icon: "waiter" },
    ],
  },
  {
    title: "Прогноз продаж",
    items: [
      { id: "forecast-branch", label: "Прогноз по филиалам", icon: "forecast" },
      { id: "forecast-compare", label: "Сравнение факт / прогноз", icon: "compare" },
    ],
  },
  {
    title: "Бонусы",
    items: [
      { id: "bonus-calc", label: "Расчёты бонусов", icon: "award" },
      { id: "bonus-scheme", label: "Схемы расчёта", icon: "formula" },
      { id: "bonus-kpi", label: "Ручной ввод KPI", icon: "edit" },
      { id: "bonus-plan", label: "Помесячные планы", icon: "plan" },
    ],
  },
  {
    title: "Справочники",
    items: [
      { id: "departments", label: "Подразделения", icon: "building" },
      { id: "employees", label: "Сотрудники", icon: "users", count: 1639 },
    ],
  },
];

const NAV_FLAT = NAV.flatMap(g => g.items);

function Sidebar({ active, onNav, collapsed }) {
  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <span className="logo">Sf</span>
        <div className="brand-text">
          <b>Sales Forecast</b>
          <span>Aqniet Holding</span>
        </div>
      </div>
      <nav style={{ flex: 1, overflowY: "auto", padding: "0 0 8px" }}>
        {NAV.map((g, gi) => (
          <div key={gi} className="sidebar__group">
            <div className="sidebar__group-title">{g.title}</div>
            {g.items.map(it => (
              <div
                key={it.id}
                className={"nav-item" + (active === it.id ? " active" : "")}
                onClick={() => onNav(it.id)}
                title={collapsed ? it.label : undefined}
              >
                <Icon name={it.icon} />
                <span className="label">{it.label}</span>
                {it.count != null && <span className="count">{AQ.fmtNum(it.count)}</span>}
              </div>
            ))}
          </div>
        ))}
      </nav>
      <div className="sidebar__footer">
        <span className="avatar">МК</span>
        <div className="meta">
          <b>Малика К.</b>
          <span>Финансовый директор</span>
        </div>
        <button className="btn btn--ghost btn--icon btn--sm footer-action" title="Настройки">
          <Icon name="settings" size={14} />
        </button>
      </div>
    </aside>
  );
}

function Topbar({ active, onNav, theme, setTheme, sidebarCollapsed, setSidebarCollapsed, openCmdK }) {
  const current = NAV_FLAT.find(i => i.id === active);
  const group = NAV.find(g => g.items.some(i => i.id === active))?.title;
  return (
    <header className="topbar">
      <button className="btn btn--ghost btn--icon btn--sm" onClick={() => setSidebarCollapsed(c => !c)} title="Свернуть/развернуть">
        <Icon name="panel" size={16} />
      </button>
      <div className="crumbs">
        <span>Aqniet</span>
        <Icon name="chevronRight" size={11} className="sep" />
        <span>{group}</span>
        <Icon name="chevronRight" size={11} className="sep" />
        <b>{current?.label}</b>
      </div>
      <div className="spacer" />
      <div className="search" onClick={openCmdK} style={{ cursor: "pointer" }}>
        <Icon name="search" size={14} style={{ color: "var(--text-subtle)" }} />
        <input readOnly placeholder="Поиск по системе…" style={{ pointerEvents: "none" }} />
        <span className="kbd">⌘ K</span>
      </div>
      <div className="topbar-actions">
        <button className="btn btn--ghost btn--icon" title="Уведомления">
          <Icon name="bell" size={16} />
          <span style={{ position: "absolute", top: 8, right: 8, width: 6, height: 6, background: "var(--neg)", borderRadius: 999 }} />
        </button>
        <button
          className="btn btn--ghost btn--icon"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          title="Сменить тему"
        >
          <Icon name={theme === "dark" ? "sun" : "moon"} size={16} />
        </button>
      </div>
    </header>
  );
}

function CmdK({ open, onClose, onNav }) {
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const inputRef = useRef(null);
  useEffect(() => { if (open) { setQ(""); setSel(0); setTimeout(() => inputRef.current?.focus(), 50); } }, [open]);
  const filtered = useMemo(() => {
    const norm = q.trim().toLowerCase();
    return NAV.flatMap(g => g.items.map(it => ({ ...it, group: g.title })))
      .filter(it => !norm || it.label.toLowerCase().includes(norm) || it.group.toLowerCase().includes(norm));
  }, [q]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowDown") { e.preventDefault(); setSel(s => Math.min(filtered.length - 1, s + 1)); }
      if (e.key === "ArrowUp") { e.preventDefault(); setSel(s => Math.max(0, s - 1)); }
      if (e.key === "Enter") { e.preventDefault(); const it = filtered[sel]; if (it) { onNav(it.id); onClose(); } }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, filtered, sel, onClose, onNav]);
  if (!open) return null;
  return (
    <div className="cmdk-overlay" onClick={onClose}>
      <div className="cmdk" onClick={e => e.stopPropagation()}>
        <div className="cmdk__input">
          <Icon name="search" size={16} style={{ color: "var(--text-muted)" }} />
          <input ref={inputRef} value={q} onChange={e => { setQ(e.target.value); setSel(0); }} placeholder="Перейти к разделу, найти филиал, сотрудника…" />
          <span className="kbd">ESC</span>
        </div>
        <div className="cmdk__list">
          {filtered.length === 0 && <div style={{ padding: 24, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>Ничего не найдено</div>}
          {(() => {
            const groups = {};
            filtered.forEach((it, i) => { (groups[it.group] = groups[it.group] || []).push({ ...it, index: i }); });
            return Object.entries(groups).map(([g, items]) => (
              <div key={g}>
                <div className="cmdk__group-title">{g}</div>
                {items.map(it => (
                  <div key={it.id} className={"cmdk__item" + (it.index === sel ? " selected" : "")}
                    onMouseEnter={() => setSel(it.index)}
                    onClick={() => { onNav(it.id); onClose(); }}>
                    <Icon name={it.icon} size={14} />
                    <span>{it.label}</span>
                    <span className="desc">Перейти →</span>
                  </div>
                ))}
              </div>
            ));
          })()}
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { Sidebar, Topbar, CmdK, NAV, NAV_FLAT });
