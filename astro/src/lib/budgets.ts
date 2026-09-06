/** Reviewed releases are selected explicitly by year; no implicit estimate preference. */
import historical from '../../../data/curated/budgets/historical.json';
import current from '../../../data/curated/budgets/mof-2026.json';

export const sectorOrder = [
  'Social Development', 'Security and External Relations',
  'Economic Development', 'Government Administration',
];
export interface BudgetRow {
  year: number;
  estimateType: 'Actual' | 'Revised' | 'Estimated';
  sector: string;
  ministry: string;
  operating: number | null;
  development: number | null;
}
interface Control { year: number; sector: string; operating: number; development: number }
export interface BudgetRelease {
  id: string;
  title: string;
  sourceUrl: string | null;
  publishedAt: string | null;
  reviewedAt: string | null;
  sourceSha256: string;
  notes: string[];
  controls: Control[];
  rows: BudgetRow[];
}
const fail = (message: string): never => { throw new Error(`Invalid budget release: ${message}`); };
const amount = (value: unknown) => value === null || (typeof value === 'number' && Number.isFinite(value) && value >= 0);

export function validateRelease(value: unknown): BudgetRelease {
  if (!value || typeof value !== 'object') return fail('expected an object');
  const release = value as BudgetRelease;
  if (!release.id || !release.title || !/^[a-f0-9]{64}$/.test(release.sourceSha256)) fail('missing provenance');
  if (!Array.isArray(release.rows) || !release.rows.length || !Array.isArray(release.controls)) fail('missing rows or controls');
  const keys = new Set<string>();
  const yearKeys = new Map<number, Set<string>>();
  const bases = new Map<number, string>();
  for (const row of release.rows) {
    if (!Number.isInteger(row.year) || !['Actual', 'Revised', 'Estimated'].includes(row.estimateType)) fail('invalid year or estimate basis');
    if (!sectorOrder.includes(row.sector) || typeof row.ministry !== 'string' || !row.ministry.trim()) fail('invalid sector or ministry');
    if (!amount(row.operating) || !amount(row.development)) fail(`invalid amount for ${row.year}/${row.ministry}`);
    const key = JSON.stringify([row.year, row.sector, row.ministry]);
    if (keys.has(key)) fail(`duplicate ${key}`);
    keys.add(key);
    if (bases.has(row.year) && bases.get(row.year) !== row.estimateType) fail(`mixed estimate bases for ${row.year}`);
    bases.set(row.year, row.estimateType);
    if (!yearKeys.has(row.year)) yearKeys.set(row.year, new Set());
    yearKeys.get(row.year)!.add(JSON.stringify([row.sector, row.ministry]));
  }
  // These releases have a fixed set of sector/ministry pairs across their years.
  // A changed classification needs a separate, explicitly reviewed release.
  const coverage = [...yearKeys.values()].map(keys => JSON.stringify([...keys].sort()));
  if (coverage.some(keys => keys !== coverage[0])) fail('incomplete or inconsistent annual coverage');
  if (release.controls.length) {
    const seen = new Set<string>();
    for (const control of release.controls) {
      if (!bases.has(control.year) || !['Total', ...sectorOrder].includes(control.sector)) fail('unknown control total');
      const key = `${control.year}/${control.sector}`;
      if (seen.has(key)) fail(`duplicate control ${key}`);
      seen.add(key);
      const rows = release.rows.filter(r => r.year === control.year && (control.sector === 'Total' || r.sector === control.sector));
      for (const kind of ['operating', 'development'] as const) {
        if (typeof control[kind] !== 'number' || !Number.isFinite(control[kind])) fail('invalid control amount');
        const sum = rows.reduce((sum, row) => sum + (row[kind] ?? 0), 0);
        // Each published component and the control can round by up to S$0.5m.
        const tolerance = (rows.filter(row => row[kind] !== null).length + 1) / 2;
        if (Math.abs(sum - control[kind]) > tolerance) fail(`${key}/${kind} does not reconcile`);
      }
    }
    if (seen.size !== bases.size * (sectorOrder.length + 1)) fail('missing annual control totals');
  }
  return release;
}

export function combineReleases(values: unknown[]) {
  const releases = values.map(validateRelease);
  const owners = new Map<number, string>();
  for (const release of releases) {
    for (const year of new Set(release.rows.map(row => row.year))) {
      if (owners.has(year)) fail(`multiple releases selected for ${year}`);
      owners.set(year, release.id);
    }
  }
  return { releases, rows: releases.flatMap(release => release.rows) };
}

export function groupBudgetYears(rows: BudgetRow[]) {
  const years = new Map<number, Map<string, {
    sector: string; ministry: string; operating: number; development: number; estimateType: string;
  }>>();
  for (const row of rows) {
    if (!years.has(row.year)) years.set(row.year, new Map());
    years.get(row.year)!.set(`${row.sector}|||${row.ministry}`, {
      sector: row.sector, ministry: row.ministry, estimateType: row.estimateType,
      // A source dash stays null in the release and contributes nothing to chart totals.
      operating: row.operating ?? 0, development: row.development ?? 0,
    });
  }
  return years;
}

export function loadBudgets() { return combineReleases([historical, current]); }
