import type { DonutSlice } from './ui/charts'

/** Every holding stays on the allocation donut. The V2 hero briefly folded
 *  the tail into a Miscellaneous slice to match Overview's 8-item cap;
 *  that hid real positions behind a grey wedge. */
export function visibleAllocationSlices(slices: DonutSlice[]): DonutSlice[] {
  return slices
}
