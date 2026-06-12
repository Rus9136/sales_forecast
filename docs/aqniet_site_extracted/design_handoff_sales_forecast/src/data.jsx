// Realistic data for Sales Forecast prototype
const fmtKZT = (v) => new Intl.NumberFormat("ru-RU").format(Math.round(v)) + " ₸";
const fmtNum = (v) => new Intl.NumberFormat("ru-RU").format(Math.round(v));
const fmtCompact = (v) => {
  const abs = Math.abs(v);
  if (abs >= 1e9) return (v / 1e9).toFixed(1).replace(".0","") + " млрд";
  if (abs >= 1e6) return (v / 1e6).toFixed(1).replace(".0","") + " млн";
  if (abs >= 1e3) return (v / 1e3).toFixed(0) + "к";
  return String(v);
};
const fmtPct = (v, d = 1) => (v >= 0 ? "+" : "") + v.toFixed(d) + "%";
const fmtDate = (d) => {
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  return `${dd}.${mm}.${d.getFullYear()}`;
};

// Pseudo-random with seed for stability
function mulberry32(seed) {
  return function () {
    let t = (seed += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rng = mulberry32(42);

const BRANCHES = [
  { id: "MDL_11", name: "Мадлен 11 мкр", city: "Алматы", manager: "Серикова А.", staff: 24 },
  { id: "MDL_OTAU", name: "Мадлен Отау", city: "Алматы", manager: "Касенов М.", staff: 19 },
  { id: "MDL_ALLEY", name: "Мадлен Аллея", city: "Алматы", manager: "Жумабай Д.", staff: 22 },
  { id: "MDL_CITY", name: "Мадлен Сити Мол", city: "Астана", manager: "Турсын А.", staff: 28 },
  { id: "MDL_VOEN", name: "Мадлен МЗ Военкомат", city: "Шымкент", manager: "Айдар Б.", staff: 18 },
  { id: "TARY_SAR", name: "Тары Сарайшык", city: "Астана", manager: "Ерлан К.", staff: 21 },
  { id: "TARY_TZ", name: "Tary Taraz", city: "Тараз", manager: "Гульмира С.", staff: 14 },
  { id: "TARY_SEM", name: "Тары Семей", city: "Семей", manager: "Бакыт М.", staff: 16 },
  { id: "SDQ_TURK", name: "Sandyq Turkestan", city: "Туркестан", manager: "Айгерим Ш.", staff: 12 },
  { id: "KAINAR_SH", name: "Kainar Shymkent", city: "Шымкент", manager: "Дияр О.", staff: 20 },
  { id: "MDL_KEN", name: "Мадлен Кенесары", city: "Астана", manager: "Аслан Р.", staff: 17 },
  { id: "TARY_AKT", name: "Тары Актобе", city: "Актобе", manager: "Гулнара Е.", staff: 15 },
];

const PRODUCT_LINES = ["Madlen", "Tary", "Sandyq", "Kainar"];

// Build 90 days of sales per branch with realistic weekly seasonality
function buildDailySales() {
  const today = new Date(2026, 3, 30); // 30 апреля 2026
  const days = 90;
  const out = [];
  let id = 25000;
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const dow = d.getDay();
    const weekend = dow === 0 || dow === 6;
    BRANCHES.forEach((b, bi) => {
      // base by branch, weekly cycle, random + slight upward trend
      const base = 350000 + bi * 80000 + (b.id.startsWith("MDL_CITY") ? 600000 : 0);
      const week = weekend ? 1.45 : (dow === 5 ? 1.25 : 1.0);
      const noise = 0.7 + rng() * 0.6;
      const trend = 1 + (days - i) * 0.0015;
      const sum = base * week * noise * trend;
      out.push({
        id: id++,
        branchId: b.id,
        branch: b.name,
        date: new Date(d),
        sum,
        created: new Date(d.getFullYear(), d.getMonth(), d.getDate(), 2, 0, 2),
        synced: new Date(d.getFullYear(), d.getMonth(), d.getDate(), 2, 0, 2),
      });
    });
  }
  return out.sort((a, b) => b.date - a.date);
}
const DAILY_SALES = buildDailySales();

// Hourly distribution for one branch / day range
function buildHourlySales(branchId, dayRange = 7) {
  const today = new Date(2026, 3, 30);
  const out = [];
  let id = 70000;
  // shape: low at night, peak at lunch (12-14) and dinner (18-20)
  const shape = [0.05,0.03,0.02,0.02,0.02,0.03,0.05,0.10,0.20,0.50,0.85,1.25,1.45,1.60,1.20,0.95,0.85,1.10,1.55,1.50,1.30,0.95,0.55,0.25];
  for (let i = dayRange - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    for (let h = 0; h < 24; h++) {
      if (shape[h] < 0.04) continue;
      const noise = 0.8 + rng() * 0.4;
      const sum = 18000 * shape[h] * noise;
      if (sum < 500) continue;
      out.push({
        id: id++,
        branchId,
        branch: BRANCHES.find(x => x.id === branchId)?.name || branchId,
        date: new Date(d),
        hour: h,
        sum,
        created: new Date(d.getFullYear(), d.getMonth(), d.getDate(), h, 5, 0),
        synced: new Date(d.getFullYear(), d.getMonth(), d.getDate(), h, 5, 0),
      });
    }
  }
  return out;
}

// Hourly heatmap aggregate (24h x 7 weekdays)
function buildHeatmap() {
  const grid = Array.from({ length: 7 }, () => Array(24).fill(0));
  const shape = [0.05,0.03,0.02,0.02,0.02,0.03,0.05,0.10,0.20,0.50,0.85,1.25,1.45,1.60,1.20,0.95,0.85,1.10,1.55,1.50,1.30,0.95,0.55,0.25];
  const dowMul = [1.05, 0.85, 0.92, 1.0, 1.10, 1.40, 1.55]; // Mon..Sun
  for (let dow = 0; dow < 7; dow++) {
    for (let h = 0; h < 24; h++) {
      grid[dow][h] = Math.round(shape[h] * dowMul[dow] * 18000 * (0.92 + rng() * 0.16));
    }
  }
  return grid;
}
const HEATMAP = buildHeatmap();

// Waiters
const FIRST_NAMES = ["Айгерим","Дария","Алия","Айдос","Мадина","Алишер","Жанат","Ерлан","Гульназ","Бакыт","Дамир","Асель","Ерасыл","Айбек","Сабина","Мерей","Динара","Тимур","Камила","Нурлан","Фарида","Адиль","Сания","Бекзат","Каролина","Илья","Анастасия","Артур"];
const LAST_NAMES = ["Касенова","Жумабай","Серикова","Турсын","Айдаров","Нуржанова","Сагынбай","Касен","Орынбасар","Жакеева","Ермекова","Алмазова","Темиргалиев","Рысбек","Турарбекова","Османова","Болатов"];

function buildWaiters() {
  const out = [];
  for (let i = 0; i < 64; i++) {
    const fn = FIRST_NAMES[Math.floor(rng() * FIRST_NAMES.length)];
    const ln = LAST_NAMES[Math.floor(rng() * LAST_NAMES.length)];
    const branch = BRANCHES[Math.floor(rng() * BRANCHES.length)];
    const checks = Math.round(85 + rng() * 220);
    const avgCheck = Math.round(7000 + rng() * 11000);
    const sum = checks * avgCheck;
    const tips = Math.round(sum * (0.04 + rng() * 0.05));
    const rating = +(4.2 + rng() * 0.8).toFixed(2);
    out.push({
      id: 6000 + i,
      name: `${fn} ${ln}`,
      branchId: branch.id,
      branch: branch.name,
      checks, avgCheck, sum, tips, rating,
      shifts: Math.round(14 + rng() * 8),
    });
  }
  return out.sort((a, b) => b.sum - a.sum);
}
const WAITERS = buildWaiters();

// Forecast — by branch, current month
function buildForecast() {
  return BRANCHES.map(b => {
    const lastMonth = (DAILY_SALES.filter(s => s.branchId === b.id).reduce((sum, s) => sum + s.sum, 0)) / 3;
    const planned = Math.round(lastMonth * (0.95 + rng() * 0.18));
    const fact = Math.round(planned * (0.78 + rng() * 0.32));
    const forecast = Math.round(planned * (0.95 + rng() * 0.18));
    return {
      branchId: b.id,
      branch: b.name,
      city: b.city,
      manager: b.manager,
      plan: planned,
      fact,
      forecast,
      progress: fact / planned,
      delta: (forecast - planned) / planned,
    };
  });
}
const FORECAST = buildForecast();

// Bonus calculations
const BONUS_SCHEMES = [
  { id: "manager_kpi", name: "Управляющий — KPI план/факт", roles: ["Управляющий"], rate: "0.5% от перевыполнения плана", base: "Выручка филиала" },
  { id: "waiter_check", name: "Официант — средний чек", roles: ["Официант"], rate: "1% при чеке > 12 000 ₸", base: "Личные продажи" },
  { id: "kitchen_speed", name: "Кухня — скорость подачи", roles: ["Повар", "Шеф"], rate: "Фикс 25 000 ₸ при < 18 мин", base: "Среднее время чека" },
  { id: "host_loyalty", name: "Хостес — постоянные гости", roles: ["Хостес"], rate: "150 ₸ за повторного гостя", base: "CRM возвраты" },
];

function buildBonusCalcs() {
  const out = [];
  for (let i = 0; i < 24; i++) {
    const branch = BRANCHES[i % BRANCHES.length];
    const scheme = BONUS_SCHEMES[i % BONUS_SCHEMES.length];
    const employee = `${FIRST_NAMES[i % FIRST_NAMES.length]} ${LAST_NAMES[(i+3) % LAST_NAMES.length]}`;
    const planFact = +(0.82 + rng() * 0.4).toFixed(3);
    const baseAmt = Math.round(800000 + rng() * 4_500_000);
    const bonus = Math.round(baseAmt * (planFact > 1 ? planFact - 1 : 0) * 0.05 + rng() * 80000);
    const status = ["Согласован","На проверке","Черновик","Согласован","Выплачен"][Math.floor(rng() * 5)];
    out.push({
      id: 1200 + i,
      period: i % 2 ? "Апрель 2026" : "Март 2026",
      branchId: branch.id, branch: branch.name,
      employee, role: scheme.roles[0], scheme: scheme.name,
      planFact, base: baseAmt, bonus, status,
    });
  }
  return out;
}
const BONUS_CALCS = buildBonusCalcs();

// Employees — mock catalog (uses scrolling — generate ~80)
const ROLES = ["Управляющий","Финансист и Главный бухгалтер","ADM 2.0 Системный Администратор","APIServerUser","Администратор зала","Хостес","Шеф","Повар","Официант","Бариста","Бухгалтер","Кассир","Курьер"];

function buildEmployees() {
  const out = [];
  for (let i = 0; i < 80; i++) {
    const fn = FIRST_NAMES[i % FIRST_NAMES.length];
    const ln = LAST_NAMES[(i + 7) % LAST_NAMES.length];
    const role = ROLES[Math.floor(rng() * ROLES.length)];
    const b1 = BRANCHES[Math.floor(rng() * BRANCHES.length)];
    const branches = rng() > 0.7 ? [b1.id] : [b1.id, BRANCHES[Math.floor(rng() * BRANCHES.length)].id];
    out.push({
      code: 1000 + i,
      sysName: `${fn.toLowerCase()}.${ln.toLowerCase()}`,
      fullName: `${ln} ${fn}`,
      role,
      branches,
      login: `${fn[0].toLowerCase()}${ln.toLowerCase()}${i % 99}`,
      email: rng() > 0.45 ? `${fn[0].toLowerCase()}${ln.toLowerCase()}@aqniet.kz` : null,
      phone: rng() > 0.55 ? `+7 7${Math.floor(rng()*9)}${Math.floor(rng()*9)} ${100 + Math.floor(rng()*900)} ${10+Math.floor(rng()*89)} ${10+Math.floor(rng()*89)}` : null,
      hired: new Date(2024 + Math.floor(rng() * 2), Math.floor(rng() * 12), 1 + Math.floor(rng() * 27)),
      active: rng() > 0.07,
    });
  }
  return out;
}
const EMPLOYEES = buildEmployees();

// Departments tree
const DEPARTMENTS = [
  { id: "ROOT", name: "Aqniet Holding", parent: null, type: "Холдинг", staff: 1639, branches: BRANCHES.length, sales: 1845_000_000 },
  { id: "MDL", name: "Madlen", parent: "ROOT", type: "Сеть", staff: 220, branches: 6, sales: 920_000_000 },
  { id: "TARY", name: "Tary", parent: "ROOT", type: "Сеть", staff: 145, branches: 4, sales: 480_000_000 },
  { id: "SDQ", name: "Sandyq", parent: "ROOT", type: "Сеть", staff: 80, branches: 3, sales: 285_000_000 },
  { id: "KAI", name: "Kainar", parent: "ROOT", type: "Сеть", staff: 62, branches: 2, sales: 160_000_000 },
];

window.AQ = {
  fmtKZT, fmtNum, fmtCompact, fmtPct, fmtDate,
  BRANCHES, DAILY_SALES, HEATMAP, WAITERS, FORECAST,
  BONUS_SCHEMES, BONUS_CALCS, EMPLOYEES, DEPARTMENTS, ROLES,
  PRODUCT_LINES,
  buildHourlySales,
};
