// === Primitives: Sparkline, MiniChart, Bars, LineChart, Heatmap cells, Checkbox, Pager ===
const { useState, useEffect, useMemo, useRef, useCallback } = React;

function Sparkline({ data, height = 32, stroke, fill }) {
  const w = 120;
  const h = height;
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const step = w / (data.length - 1);
  const pts = data.map((v, i) => {
    const x = i * step;
    const y = h - ((v - min) / range) * (h - 4) - 2;
    return [x, y];
  });
  const d = pts.map((p, i) => (i === 0 ? `M${p[0]},${p[1]}` : `L${p[0]},${p[1]}`)).join(" ");
  const fillD = `${d} L${w},${h} L0,${h} Z`;
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      <path d={fillD} fill={fill || "var(--accent-soft)"} opacity="0.7" />
      <path d={d} fill="none" stroke={stroke || "var(--accent)"} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Bars({ data, labels, height = 320, format = AQ.fmtCompact, accent = "var(--accent)" }) {
  const ref = useRef(null);
  const [hover, setHover] = useState(null);
  const [box, setBox] = useState({ w: 800, h: height });
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(es => {
      const r = es[0].contentRect;
      setBox({ w: r.width, h: height });
    });
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, [height]);
  const pad = { l: 48, r: 14, t: 14, b: 30 };
  const innerW = Math.max(0, box.w - pad.l - pad.r);
  const innerH = box.h - pad.t - pad.b;
  const max = Math.max(...data, 1);
  const niceMax = Math.ceil(max / 5) * 5 || 5;
  const ticks = 5;
  const barW = (innerW / data.length) * 0.6;
  const gap = (innerW / data.length) * 0.4;

  return (
    <div ref={ref} style={{ width: "100%", height }}>
      <svg width="100%" height={box.h} viewBox={`0 0 ${box.w} ${box.h}`}>
        {/* grid */}
        {Array.from({ length: ticks + 1 }).map((_, i) => {
          const y = pad.t + (innerH * i) / ticks;
          const val = niceMax - (niceMax * i) / ticks;
          return (
            <g key={i}>
              <line x1={pad.l} x2={box.w - pad.r} y1={y} y2={y} stroke="var(--chart-grid)" strokeWidth="1" strokeDasharray={i === ticks ? "0" : "2 3"} />
              <text x={pad.l - 8} y={y + 3.5} fontSize="10.5" textAnchor="end" fill="var(--chart-axis)" fontFamily="var(--font-mono)">{format(val)}</text>
            </g>
          );
        })}
        {/* bars */}
        {data.map((v, i) => {
          const bh = (v / niceMax) * innerH;
          const x = pad.l + i * (barW + gap) + gap / 2;
          const y = pad.t + innerH - bh;
          const isHover = hover === i;
          return (
            <g key={i} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect x={x} y={pad.t} width={barW} height={innerH} fill="transparent" />
              <rect
                x={x}
                y={y}
                width={barW}
                height={Math.max(2, bh)}
                rx="2"
                fill={isHover ? "oklch(from " + accent + " calc(l - 0.05) c h)" : accent}
                opacity={hover != null && !isHover ? 0.45 : 1}
              />
            </g>
          );
        })}
        {/* axis labels */}
        {labels.map((l, i) => {
          const x = pad.l + i * (barW + gap) + gap / 2 + barW / 2;
          const show = labels.length <= 24 || i % Math.ceil(labels.length / 16) === 0;
          if (!show) return null;
          return (
            <text key={i} x={x} y={box.h - 8} fontSize="10.5" textAnchor="middle" fill="var(--chart-axis)" fontFamily="var(--font-mono)">{l}</text>
          );
        })}
        {/* tooltip */}
        {hover != null && (
          <g pointerEvents="none">
            <rect
              x={pad.l + hover * (barW + gap) + gap / 2 + barW + 6}
              y={pad.t + innerH - (data[hover] / niceMax) * innerH - 28}
              width={94} height={26} rx="4"
              fill="var(--text)" opacity="0.92"
            />
            <text
              x={pad.l + hover * (barW + gap) + gap / 2 + barW + 53}
              y={pad.t + innerH - (data[hover] / niceMax) * innerH - 11}
              fontSize="11" textAnchor="middle" fontFamily="var(--font-mono)" fill="var(--bg)"
            >{format(data[hover])}</text>
          </g>
        )}
      </svg>
    </div>
  );
}

function LineChart({ series, labels, height = 280, format = AQ.fmtCompact, showLegend = true }) {
  const ref = useRef(null);
  const [hover, setHover] = useState(null);
  const [box, setBox] = useState({ w: 800, h: height });
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(es => setBox({ w: es[0].contentRect.width, h: height }));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, [height]);
  const pad = { l: 48, r: 14, t: 14, b: 30 };
  const innerW = Math.max(0, box.w - pad.l - pad.r);
  const innerH = box.h - pad.t - pad.b;
  const all = series.flatMap(s => s.data);
  const max = Math.max(...all, 1);
  const niceMax = Math.ceil(max / 5) * 5 || 5;
  const ticks = 5;
  const n = labels.length;
  const xStep = n <= 1 ? innerW : innerW / (n - 1);

  const path = (data) => data.map((v, i) => {
    const x = pad.l + i * xStep;
    const y = pad.t + innerH - (v / niceMax) * innerH;
    return (i === 0 ? "M" : "L") + x.toFixed(1) + "," + y.toFixed(1);
  }).join(" ");

  return (
    <div ref={ref} style={{ width: "100%", height, position: "relative" }}>
      <svg width="100%" height={box.h} viewBox={`0 0 ${box.w} ${box.h}`}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const x = e.clientX - rect.left - pad.l;
          const idx = Math.round(x / xStep);
          if (idx >= 0 && idx < n) setHover(idx);
        }}
      >
        {Array.from({ length: ticks + 1 }).map((_, i) => {
          const y = pad.t + (innerH * i) / ticks;
          const val = niceMax - (niceMax * i) / ticks;
          return (
            <g key={i}>
              <line x1={pad.l} x2={box.w - pad.r} y1={y} y2={y} stroke="var(--chart-grid)" strokeDasharray={i === ticks ? "0" : "2 3"} />
              <text x={pad.l - 8} y={y + 3.5} fontSize="10.5" textAnchor="end" fill="var(--chart-axis)" fontFamily="var(--font-mono)">{format(val)}</text>
            </g>
          );
        })}
        {labels.map((l, i) => {
          const x = pad.l + i * xStep;
          const show = labels.length <= 16 || i % Math.ceil(labels.length / 10) === 0;
          if (!show) return null;
          return <text key={i} x={x} y={box.h - 8} fontSize="10.5" textAnchor="middle" fill="var(--chart-axis)" fontFamily="var(--font-mono)">{l}</text>;
        })}
        {series.map((s, si) => (
          <g key={si}>
            {s.area && (
              <path
                d={`${path(s.data)} L${pad.l + (n - 1) * xStep},${pad.t + innerH} L${pad.l},${pad.t + innerH} Z`}
                fill={s.color || "var(--accent)"} opacity="0.10"
              />
            )}
            <path d={path(s.data)} fill="none" stroke={s.color || "var(--accent)"} strokeWidth={s.width || 2}
              strokeDasharray={s.dashed ? "4 4" : "0"} strokeLinecap="round" strokeLinejoin="round" />
          </g>
        ))}
        {hover != null && (
          <g pointerEvents="none">
            <line
              x1={pad.l + hover * xStep} x2={pad.l + hover * xStep}
              y1={pad.t} y2={pad.t + innerH}
              stroke="var(--text-subtle)" strokeWidth="1" strokeDasharray="3 3"
            />
            {series.map((s, si) => {
              const v = s.data[hover];
              const x = pad.l + hover * xStep;
              const y = pad.t + innerH - (v / niceMax) * innerH;
              return <circle key={si} cx={x} cy={y} r="3.5" fill={s.color || "var(--accent)"} stroke="var(--surface)" strokeWidth="2" />;
            })}
          </g>
        )}
      </svg>
      {hover != null && (
        <div style={{
          position: "absolute",
          left: Math.min(box.w - 180, pad.l + hover * xStep + 12),
          top: pad.t + 4,
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 8,
          padding: "8px 10px",
          fontSize: 12,
          boxShadow: "var(--shadow-md)",
          minWidth: 140,
          pointerEvents: "none",
        }}>
          <div style={{ color: "var(--text-muted)", marginBottom: 4, fontSize: 11 }}>{labels[hover]}</div>
          {series.map((s, si) => (
            <div key={si} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: s.color || "var(--accent)" }} />
                {s.name}
              </span>
              <b style={{ fontVariantNumeric: "tabular-nums", fontFamily: "var(--font-mono)" }}>{format(s.data[hover])}</b>
            </div>
          ))}
        </div>
      )}
      {showLegend && (
        <div style={{ position: "absolute", top: 10, right: 14, display: "flex", gap: 14, fontSize: 12, color: "var(--text-muted)" }}>
          {series.map((s, si) => (
            <span key={si} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <span style={{
                width: 14, height: 2, borderRadius: 1, background: s.color || "var(--accent)",
                borderTop: s.dashed ? `2px dashed ${s.color || "var(--accent)"}` : undefined,
                background: s.dashed ? "transparent" : (s.color || "var(--accent)"),
                borderBottom: s.dashed ? `2px dashed ${s.color || "var(--accent)"}` : undefined,
              }} />
              {s.name}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function Checkbox({ checked, indeterminate, onChange }) {
  return (
    <span
      className={"checkbox" + (checked ? " checked" : "") + (indeterminate ? " indeterminate" : "")}
      role="checkbox"
      tabIndex={0}
      aria-checked={checked}
      onClick={(e) => { e.stopPropagation(); onChange?.(!checked); }}
      onKeyDown={(e) => { if (e.key === " " || e.key === "Enter") { e.preventDefault(); onChange?.(!checked); } }}
    >
      {checked && <Icon name="check" size={10} className="" />}
      {indeterminate && !checked && <span style={{ width: 8, height: 2, background: "var(--accent-fg)", borderRadius: 1 }} />}
    </span>
  );
}

function Pager({ page, pages, onPage }) {
  const items = [];
  const push = (p) => items.push(p);
  if (pages <= 7) {
    for (let i = 1; i <= pages; i++) push(i);
  } else {
    push(1);
    if (page > 3) push("…");
    for (let i = Math.max(2, page - 1); i <= Math.min(pages - 1, page + 1); i++) push(i);
    if (page < pages - 2) push("…");
    push(pages);
  }
  return (
    <div className="pager">
      <button className="page" disabled={page === 1} onClick={() => onPage(1)}><Icon name="chevronsLeft" size={12} /></button>
      <button className="page" disabled={page === 1} onClick={() => onPage(page - 1)}><Icon name="chevronLeft" size={12} /></button>
      {items.map((it, i) => it === "…"
        ? <span key={i} className="page" style={{ cursor: "default" }}>…</span>
        : <button key={i} className={"page" + (it === page ? " active" : "")} onClick={() => onPage(it)}>{it}</button>
      )}
      <button className="page" disabled={page === pages} onClick={() => onPage(page + 1)}><Icon name="chevronRight" size={12} /></button>
      <button className="page" disabled={page === pages} onClick={() => onPage(pages)}><Icon name="chevronsRight" size={12} /></button>
    </div>
  );
}

function ThSort({ children, k, sort, onSort, align = "left", sticky }) {
  const active = sort?.k === k;
  const dir = active ? sort.d : null;
  const cls = ["sortable", active ? "sorted" : "", sticky ? "stick-l" : ""].filter(Boolean).join(" ");
  return (
    <th className={cls} style={{ textAlign: align }} onClick={() => onSort?.(k)}>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
        {children}
        <span className="sort">
          {!active && <Icon name="sort" size={11} />}
          {active && dir === "asc" && <Icon name="sortAsc" size={11} />}
          {active && dir === "desc" && <Icon name="sortDesc" size={11} />}
        </span>
      </span>
    </th>
  );
}

function useSortable(rows, initialKey, initialDir = "desc") {
  const [sort, setSort] = useState({ k: initialKey, d: initialDir });
  const onSort = (k) => setSort(s => s.k === k ? { k, d: s.d === "asc" ? "desc" : "asc" } : { k, d: "desc" });
  const sorted = useMemo(() => {
    if (!sort.k) return rows;
    const copy = [...rows];
    copy.sort((a, b) => {
      const av = a[sort.k]; const bv = b[sort.k];
      if (av == null) return 1;
      if (bv == null) return -1;
      if (av < bv) return sort.d === "asc" ? -1 : 1;
      if (av > bv) return sort.d === "asc" ? 1 : -1;
      return 0;
    });
    return copy;
  }, [rows, sort]);
  return { sorted, sort, onSort };
}

Object.assign(window, { Sparkline, Bars, LineChart, Checkbox, Pager, ThSort, useSortable });
