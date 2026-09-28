import type { SVGProps } from "react";

export type IconName =
  | "catchment"
  | "chevron"
  | "close"
  | "copy"
  | "hydrology"
  | "layers"
  | "reservoirs"
  | "search"
  | "thames-discharge"
  | "water-quality"
  | "water-supply";

const paths: Record<IconName, React.ReactNode> = {
  catchment: <><path d="M3 7.5 12 3l9 4.5-9 4.5-9-4.5Z"/><path d="m5 11 7 3.5 7-3.5M5 15l7 3.5 7-3.5"/></>,
  chevron: <path d="m7 9 5 5 5-5"/>,
  close: <path d="m6 6 12 12M18 6 6 18"/>,
  copy: <><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></>,
  hydrology: <><path d="M12 3C9.5 6.4 6 9.9 6 14a6 6 0 0 0 12 0c0-4.1-3.5-7.6-6-11Z"/><path d="M9 15.5c.8 1.4 1.8 2 3.3 2"/></>,
  layers: <><path d="m3 7 9-4 9 4-9 4-9-4Z"/><path d="m3 12 9 4 9-4M3 17l9 4 9-4"/></>,
  reservoirs: <><path d="M4 8c2 0 2-2 4-2s2 2 4 2 2-2 4-2 2 2 4 2"/><path d="M4 13c2 0 2-2 4-2s2 2 4 2 2-2 4-2 2 2 4 2M4 18c2 0 2-2 4-2s2 2 4 2 2-2 4-2 2 2 4 2"/></>,
  search: <><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></>,
  "thames-discharge": <><path d="M4 5h10v5H9v4"/><path d="M9 14c-1.6 2-2.5 3.1-2.5 4.2a2.5 2.5 0 0 0 5 0C11.5 17.1 10.6 16 9 14ZM14 7h6"/></>,
  "water-quality": <><path d="M12 3C9 7 6.5 10 6.5 14a5.5 5.5 0 0 0 11 0C17.5 10 15 7 12 3Z"/><path d="m9.5 14 1.6 1.6 3.6-4"/></>,
  "water-supply": <><path d="M4 19V9l8-5 8 5v10"/><path d="M8 19v-5h8v5M3 19h18"/></>,
};

export function Icon({ name, ...props }: { name: IconName } & SVGProps<SVGSVGElement>) {
  return <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name]}</svg>;
}
