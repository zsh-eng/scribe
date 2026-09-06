import { describe, expect, test } from 'bun:test';
import current from '../../data/curated/budgets/mof-2026.json';
import { combineReleases, groupBudgetYears, loadBudgets, validateRelease } from '../src/lib/budgets';

const clone = () => JSON.parse(JSON.stringify(current));

describe('reviewed budget data', () => {
  test('loads a single complete release per year', () => {
    const { rows } = loadBudgets();
    const years = groupBudgetYears(rows);
    expect(years.size).toBe(30);
    expect([...years.get(2025)!.values()].every(row => row.estimateType === 'Revised')).toBe(true);
    expect([...years.get(2024)!.values()].every(row => row.estimateType === 'Actual')).toBe(true);
    expect([...years.get(2026)!.values()].every(row => row.estimateType === 'Estimated')).toBe(true);
  });
  test('excludes other fund outlays and preserves multi-sector allocations', () => {
    const { rows } = loadBudgets();
    const mnd = rows.find(row => row.year === 2026 && row.ministry === 'National Development')!;
    // MOF Analysis FY2026, Table 3.5 p30; detailed estimates p180 separate other outlays.
    expect(mnd.development).toBe(1447);
    expect(rows.filter(row => row.year === 2026 && row.ministry === 'Manpower')).toHaveLength(2);
    expect(rows.filter(row => row.year === 2026 && row.ministry === 'Digital Development and Information')).toHaveLength(3);
    const total = rows.filter(row => row.year === 2026).reduce((s, r) => s + (r.operating ?? 0) + (r.development ?? 0), 0);
    expect(total).toBe(137325); // Rounded components; published control is 137323.
  });
  test('preserves source dashes without accepting malformed numbers', () => {
    expect(current.rows.find(r => r.year === 2026 && r.sector === 'Social Development' && r.ministry === 'Manpower')!.development).toBeNull();
    for (const bad of ['', 'unknown', -1, NaN, Infinity, undefined]) {
      const data = clone();
      data.rows[0].operating = bad;
      expect(() => validateRelease(data)).toThrow('invalid amount');
    }
  });
  test('rejects missing coverage, duplicate rows and mixed estimate bases', () => {
    const missing = clone(); missing.rows.pop();
    expect(() => validateRelease(missing)).toThrow('coverage');
    const duplicate = clone(); duplicate.rows.push(duplicate.rows[0]);
    expect(() => validateRelease(duplicate)).toThrow('duplicate');
    const mixed = clone(); mixed.rows[0].estimateType = 'Estimated';
    expect(() => validateRelease(mixed)).toThrow('mixed');
  });
  test('rejects totals outside published rounding tolerance', () => {
    const data = clone(); data.rows[0].operating += 100;
    expect(() => validateRelease(data)).toThrow('reconcile');
    const missingControl = clone(); missingControl.controls.pop();
    expect(() => validateRelease(missingControl)).toThrow('control totals');
  });
  test('requires explicit selection rather than silently combining vintages', () => {
    expect(() => combineReleases([current, current])).toThrow('multiple releases');
  });
});
