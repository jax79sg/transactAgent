/** Issue #17: a bare amount with no +/- or color gives no way to tell inflow from
 * outflow at a glance -- unlike TransactionsPage's own separate Out-flow/In-flow
 * columns, tables that only have room for one Amount column (Review's proposal and
 * disagreement tables) need the direction folded into that single cell instead. */
export function FlowAmount({ outFlow, inFlow }: { outFlow: string | null; inFlow: string | null }) {
  if (inFlow != null) {
    return <span className="text-emerald-700 dark:text-emerald-400">+{inFlow}</span>;
  }
  if (outFlow != null) {
    return <span className="text-slate-700 dark:text-slate-300">-{outFlow}</span>;
  }
  return null;
}
