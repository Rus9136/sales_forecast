// Icon set — outlined, 16px stroke. Returns React element.
const Icon = ({ name, size = 16, className = "icon", ...rest }) => {
  const paths = ICONS[name];
  if (!paths) return null;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      {...rest}
    >
      {paths}
    </svg>
  );
};

const ICONS = {
  dashboard: (<><rect x="2" y="2" width="5" height="6" rx="1" /><rect x="9" y="2" width="5" height="3" rx="1" /><rect x="2" y="10" width="5" height="4" rx="1" /><rect x="9" y="7" width="5" height="7" rx="1" /></>),
  building: (<><rect x="2.5" y="2.5" width="11" height="11" rx="1" /><path d="M5 5h1M7.5 5h1M10 5h1M5 8h1M7.5 8h1M10 8h1M5 11h1M7.5 11h1M10 11h1" /></>),
  users: (<><circle cx="6" cy="5.5" r="2.2" /><path d="M2 13.5c0-2.2 1.8-3.7 4-3.7s4 1.5 4 3.7" /><circle cx="11.5" cy="6" r="1.7" /><path d="M10.5 9.6c2 .2 3.4 1.6 3.4 3.4" /></>),
  calendar: (<><rect x="2" y="3" width="12" height="11" rx="1.4" /><path d="M2 6h12M5 1.5v3M11 1.5v3" /></>),
  clock: (<><circle cx="8" cy="8" r="6" /><path d="M8 4.5V8l2 2" /></>),
  waiter: (<><path d="M5 3.5h6l-.7 4.5H5.7L5 3.5z" /><circle cx="8" cy="10.5" r="0.6" fill="currentColor" /><path d="M2.5 14h11" /></>),
  forecast: (<><path d="M2 12L6 7l3 3 5-7" /><path d="M11 3h3v3" /></>),
  compare: (<><path d="M3 5h8M11 5l-2-2M11 5l-2 2" /><path d="M13 11H5M5 11l2-2M5 11l2 2" /></>),
  award: (<><circle cx="8" cy="6.5" r="3.5" /><path d="M5.5 9.5L4.5 14l3.5-2 3.5 2-1-4.5" /></>),
  formula: (<><path d="M3 13h2c.7 0 1-.4 1.2-1L8 4c.2-.6.5-1 1.2-1H11" /><path d="M5 8h5M11 11l2-2M13 11l-2-2" /></>),
  edit: (<><path d="M2.5 13.5l1-3 7.5-7.5 2 2L5.5 12.5l-3 1z" /></>),
  plan: (<><rect x="2" y="2.5" width="11" height="11" rx="1" /><path d="M5 6h6M5 8.5h6M5 11h4" /></>),
  refresh: (<><path d="M13 7c-.5-2.5-2.7-4.3-5.3-4-2 .3-3.6 1.8-4 3.8" /><path d="M3 9c.5 2.5 2.7 4.3 5.3 4 2-.3 3.6-1.8 4-3.8" /><path d="M11.5 4v3h-3M4.5 12V9h3" /></>),
  search: (<><circle cx="7" cy="7" r="4.5" /><path d="M10.5 10.5l3 3" /></>),
  bell: (<><path d="M4 11.5V7c0-2.2 1.8-4 4-4s4 1.8 4 4v4.5h1.5H2.5H4z" /><path d="M6.5 13.5c.4.6 1 1 1.5 1s1.1-.4 1.5-1" /></>),
  sun: (<><circle cx="8" cy="8" r="3" /><path d="M8 1.5v1.5M8 13v1.5M14.5 8H13M3 8H1.5M12.6 3.4l-1 1M5.4 11.6l-1 1M12.6 12.6l-1-1M5.4 4.4l-1-1" /></>),
  moon: (<><path d="M13 9.5A6 6 0 116.5 3a4.5 4.5 0 006.5 6.5z" /></>),
  check: (<><path d="M3 8.5L6 11.5l7-7" /></>),
  chevronDown: (<><path d="M3.5 6L8 10.5 12.5 6" /></>),
  chevronRight: (<><path d="M6 3.5L10.5 8 6 12.5" /></>),
  chevronLeft: (<><path d="M10 3.5L5.5 8 10 12.5" /></>),
  chevronsLeft: (<><path d="M9 3.5L4.5 8 9 12.5M13 3.5L8.5 8 13 12.5" /></>),
  chevronsRight: (<><path d="M3 3.5L7.5 8 3 12.5M7 3.5L11.5 8 7 12.5" /></>),
  arrowUp: (<><path d="M8 3v10M4 7l4-4 4 4" /></>),
  arrowDown: (<><path d="M8 13V3M4 9l4 4 4-4" /></>),
  upRight: (<><path d="M5 11L11 5M6 5h5v5" /></>),
  download: (<><path d="M8 2.5v8M5 8l3 3 3-3M3 13.5h10" /></>),
  upload: (<><path d="M8 13V5M5 7l3-3 3 3M3 13.5h10" /></>),
  filter: (<><path d="M2 3h12L9.5 8.5V13L6.5 14V8.5L2 3z" /></>),
  more: (<><circle cx="3.5" cy="8" r="1" fill="currentColor" /><circle cx="8" cy="8" r="1" fill="currentColor" /><circle cx="12.5" cy="8" r="1" fill="currentColor" /></>),
  close: (<><path d="M3.5 3.5l9 9M12.5 3.5l-9 9" /></>),
  plus: (<><path d="M8 3v10M3 8h10" /></>),
  sortAsc: (<><path d="M4 11l3 3 3-3M7 14V2" /></>),
  sortDesc: (<><path d="M4 5l3-3 3 3M7 2v12" /></>),
  sort: (<><path d="M5 5l-2 2M3 7h4M3 7l2-2" /><path d="M11 11l2-2M13 9h-4M13 9l-2 2" /></>),
  panel: (<><rect x="2.5" y="2.5" width="11" height="11" rx="1" /><path d="M6.5 2.5v11" /></>),
  settings: (<><circle cx="8" cy="8" r="2" /><path d="M8 1.5v2M8 12.5v2M14.5 8h-2M3.5 8h-2M12.6 3.4l-1.5 1.5M4.9 11.1l-1.5 1.5M12.6 12.6l-1.5-1.5M4.9 4.9L3.4 3.4" /></>),
  logout: (<><path d="M6 3.5H3v9h3M9 5l3 3-3 3M12 8H6" /></>),
  database: (<><ellipse cx="8" cy="3.5" rx="5.5" ry="1.5" /><path d="M2.5 3.5v9c0 .8 2.5 1.5 5.5 1.5s5.5-.7 5.5-1.5v-9" /><path d="M2.5 8c0 .8 2.5 1.5 5.5 1.5s5.5-.7 5.5-1.5" /></>),
  fire: (<><path d="M8 14c2.5 0 4.5-2 4.5-4.5 0-2-1.2-3-2-4-.7-.8-.5-2.5-.5-2.5S8.5 4 7 6c-1 1.4-3.5 2-3.5 4.5C3.5 12.5 5.5 14 8 14z" /></>),
  trending: (<><path d="M2 12L6 8l3 3 5-7M11 4h3v3" /></>),
  tag: (<><path d="M2.5 8.5l5.5 5.5L14 8 8.5 2.5h-6v6z" /><circle cx="5.5" cy="5.5" r="0.6" fill="currentColor" /></>),
  pin: (<><path d="M5 2h6v3l-1 1v3l2 2v.5H4V11l2-2V6L5 5V2z" /><path d="M8 11.5V14" /></>),
};

window.Icon = Icon;
