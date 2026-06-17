/**
 * Pure allocation logic for the Bot Budget Rebalancer.
 *
 * Rules:
 * - Dragging a slider down leaves the other bots alone (total just shrinks).
 * - Dragging a slider up is allowed while total <= max_total_pct.
 * - If dragging up would exceed max_total_pct, steal from unlocked bots
 *   starting with the one that currently has the most allocation (most to give).
 * - Locked bots are never adjusted by redistribution.
 * - Bound bots move together with the dragged bot.
 */

export interface RebalancerSlot {
  bot_id: number
  enabled: boolean
  target_pct: number
  locked: boolean
  bound: boolean
}

const snap = (v: number): number => Math.round(v * 2) / 2

/**
 * Compute the next slot states after dragging one bot's slider.
 */
export function redistributeSlots(
  slots: RebalancerSlot[],
  maxPct: number,
  draggedBotId: number,
  newValue: number,
): RebalancerSlot[] {
  const currentSlot = slots.find((s) => s.bot_id === draggedBotId)
  if (!currentSlot || !currentSlot.enabled) return slots

  const isBound = currentSlot.bound

  // 1. Clamp the new value for the dragged bot (and bound partners).
  const clamped = Math.min(Math.max(0, newValue), maxPct)

  // Bound bots move together with the dragged bot.
  const boundSlots = isBound ? slots.filter((s) => s.enabled && s.bound) : []
  const numBound = boundSlots.length > 0 ? boundSlots.length : 1

  // 2. Determine fixed allocations that cannot be touched.
  const fixedTotal = slots
    .filter((s) => s.enabled && s.locked)
    .reduce((sum, s) => sum + s.target_pct, 0)

  // 3. Compute the total the dragged group will occupy.
  const draggedGroupTotal = clamped * numBound

  // 4. Quick path: if the projected total fits under the cap, leave everyone else alone.
  const othersTotal = slots
    .filter((s) => s.enabled && s.bot_id !== draggedBotId && !(isBound && s.bound))
    .reduce((sum, s) => sum + s.target_pct, 0)
  const projectedTotal = draggedGroupTotal + fixedTotal + othersTotal

  if (projectedTotal <= maxPct) {
    return slots.map((s) => {
      if (s.enabled && ((isBound && s.bound) || s.bot_id === draggedBotId)) {
        return { ...s, target_pct: snap(clamped) }
      }
      return s
    })
  }

  // 5. Need to steal from others. Cap the dragged group to what is available
  //    after locked bots, with all bound partners sharing equally.
  const roomForDraggedGroup = Math.max(0, maxPct - fixedTotal)
  const finalDraggedValue = snap(Math.min(clamped, roomForDraggedGroup / numBound))

  // 6. Identify victims: enabled, unlocked, not dragged, not bound to dragged.
  const victims = slots.filter(
    (s) =>
      s.enabled &&
      !s.locked &&
      s.bot_id !== draggedBotId &&
      !(isBound && s.bound),
  )

  // 7. Compute how much we need to reclaim from victims.
  const desiredDraggedTotal = finalDraggedValue * numBound
  const availableForOthers = Math.max(0, maxPct - desiredDraggedTotal - fixedTotal)
  const currentVictimsTotal = victims.reduce((sum, s) => sum + s.target_pct, 0)
  let reclaim = Math.max(0, currentVictimsTotal - availableForOthers)

  // 8. Steal from the largest victim first.
  const sortedVictims = [...victims].sort((a, b) => b.target_pct - a.target_pct)
  const victimAdjustments = new Map<number, number>()

  for (const victim of sortedVictims) {
    if (reclaim <= 0.001) break
    const take = Math.min(victim.target_pct, reclaim)
    victimAdjustments.set(victim.bot_id, -take)
    reclaim -= take
  }

  // 9. Build new slots.
  return slots.map((s) => {
    if (s.enabled && ((isBound && s.bound) || s.bot_id === draggedBotId)) {
      return { ...s, target_pct: finalDraggedValue }
    }
    if (victimAdjustments.has(s.bot_id)) {
      return { ...s, target_pct: snap(Math.max(0, s.target_pct + victimAdjustments.get(s.bot_id)!)) }
    }
    return s
  })
}
