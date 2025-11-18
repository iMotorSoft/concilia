import { writable } from "svelte/store";

export const DEFAULT_DAYS_WINDOW = 5;

export const daysWindowStore = writable<number>(DEFAULT_DAYS_WINDOW);

export function normalizeDaysWindow(value: number | string | null | undefined): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.max(1, Math.round(value));
  }
  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return Math.max(1, Math.round(parsed));
    }
  }
  return DEFAULT_DAYS_WINDOW;
}
