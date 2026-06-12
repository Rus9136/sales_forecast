// === Main App ===
const { useState: useS, useEffect: useE } = React;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme": "light",
  "accent": "emerald",
  "density": "cozy",
  "sidebarCollapsed": false
}/*EDITMODE-END*/;

const SCREENS = {
  "dashboard": Dashboard,
  "sales-day": SalesByDay,
  "sales-hour": SalesByHour,
  "sales-waiter": SalesByWaiter,
  "forecast-branch": ForecastByBranch,
  "forecast-compare": FactVsForecast,
  "bonus-calc": Bonuses,
  "bonus-scheme": Bonuses,
  "bonus-kpi": Bonuses,
  "bonus-plan": Bonuses,
  "employees": Employees,
  "departments": Departments,
};

function App() {
  const [tweaks, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [active, setActive] = useS("dashboard");
  const [cmdkOpen, setCmdkOpen] = useS(false);

  useE(() => {
    document.documentElement.setAttribute("data-theme", tweaks.theme);
    document.documentElement.setAttribute("data-accent", tweaks.accent);
    document.documentElement.setAttribute("data-density", tweaks.density);
    document.documentElement.setAttribute("data-sidebar", tweaks.sidebarCollapsed ? "collapsed" : "expanded");
  }, [tweaks]);

  useE(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCmdkOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const Screen = SCREENS[active] || Dashboard;

  return (
    <div className="app" data-screen-label={active}>
      <Sidebar active={active} onNav={setActive} collapsed={tweaks.sidebarCollapsed} />
      <div className="main">
        <Topbar
          active={active}
          onNav={setActive}
          theme={tweaks.theme}
          setTheme={(v) => setTweak("theme", v)}
          sidebarCollapsed={tweaks.sidebarCollapsed}
          setSidebarCollapsed={(fn) => setTweak("sidebarCollapsed", typeof fn === "function" ? fn(tweaks.sidebarCollapsed) : fn)}
          openCmdK={() => setCmdkOpen(true)}
        />
        <div className="content">
          <Screen goto={setActive} />
        </div>
      </div>
      <CmdK open={cmdkOpen} onClose={() => setCmdkOpen(false)} onNav={setActive} />

      <TweaksPanel title="Tweaks">
        <TweakSection title="Внешний вид">
          <TweakRadio label="Тема" value={tweaks.theme} options={[
            { value: "light", label: "Светлая" },
            { value: "dark", label: "Тёмная" },
          ]} onChange={(v) => setTweak("theme", v)} />

          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 6, fontWeight: 500, textTransform: "uppercase", letterSpacing: ".04em" }}>Акцент</div>
            <div className="tw-accents">
              {[
                { id: "emerald", c: "oklch(0.62 0.13 162)", l: "Emerald" },
                { id: "indigo", c: "oklch(0.55 0.16 264)", l: "Indigo" },
                { id: "amber", c: "oklch(0.70 0.15 70)", l: "Amber" },
                { id: "slate", c: "oklch(0.30 0.014 240)", l: "Slate" },
              ].map(a => (
                <div key={a.id} className={"tw-accent" + (tweaks.accent === a.id ? " active" : "")} onClick={() => setTweak("accent", a.id)}>
                  <span className="sw" style={{ background: a.c }}></span>{a.l}
                </div>
              ))}
            </div>
          </div>

          <TweakRadio label="Плотность" value={tweaks.density} options={[
            { value: "compact", label: "Плотная" },
            { value: "cozy", label: "Средняя" },
            { value: "spacious", label: "Просторная" },
          ]} onChange={(v) => setTweak("density", v)} />

          <TweakToggle label="Свернуть боковое меню" checked={tweaks.sidebarCollapsed} onChange={(v) => setTweak("sidebarCollapsed", v)} />
        </TweakSection>
      </TweaksPanel>
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
