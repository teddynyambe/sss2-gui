/** J1939 SPN decode utilities — pure functions, no side effects. */

import type { SPNValue } from '$lib/stores/deviceStore.svelte';

export interface SPNDef {
  spn: number;
  label: string;
  bit_offset: number;
  length: number;
  scale: number;
  offset: number;
  unit: string;
  range_max: number | null;
}

export interface PGNInfo {
  label: string;
  acronym: string;
  spns: SPNDef[];
}

export type SpnDb = Record<string, PGNInfo>;

export function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++)
    bytes[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return bytes;
}

export function extractBits(data: Uint8Array, bitOffset: number, length: number): number | null {
  if (bitOffset + length > data.length * 8) return null;
  let val = 0;
  for (let i = 0; i < length; i++) {
    const byteIdx = Math.floor((bitOffset + i) / 8);
    const bitIdx = (bitOffset + i) % 8;
    if ((data[byteIdx] >> bitIdx) & 1) val |= (1 << i);
  }
  return val;
}

export function decodeSPNsFromFrame(
  pgn: string,
  data: string,
  db: SpnDb,
  arb_id: string = ''
): Record<string, SPNValue> {
  const pgnDec = parseInt(pgn, 16).toString();
  const pgInfo = db[pgnDec];
  if (!pgInfo) return {};
  const dataBytes = hexToBytes(data);
  const result: Record<string, SPNValue> = {};
  for (const spn of pgInfo.spns) {
    const raw = extractBits(dataBytes, spn.bit_offset, spn.length);
    if (raw === null) continue;
    // Skip J1939 error (all 1s) and not-available (all 1s minus 1) indicators
    const maxRaw = (1 << spn.length) - 1;
    if (raw >= maxRaw - 1) continue;
    const physical = raw * spn.scale + spn.offset;
    const key = String(spn.spn);
    result[key] = {
      spn: spn.spn,
      pgn,
      arb_id,
      label: spn.label,
      value: physical,
      unit: spn.unit,
      spec_min: spn.offset,
      spec_max: spn.range_max,
    };
  }
  return result;
}
