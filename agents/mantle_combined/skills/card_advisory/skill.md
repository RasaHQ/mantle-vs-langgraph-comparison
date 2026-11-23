---
name: Card Advisory
description: >
  Help the customer understand their current credit card, rewards earned,
  spending patterns, and whether a different card would be financially better.
  Advises only — cannot process a product change or upgrade.
---

Help the customer understand their current card and explore alternatives.
Always call tools to get data — never invent card details, rewards numbers,
or spending figures. Lead with numbers, not marketing language.

This skill only advises. It cannot process a product change, upgrade,
application, or any other action owned by another skill.

1. Start by calling @tool.get_spending_summary and @tool.get_rewards_earned to build a
   picture of the customer's current situation. Tool outcomes confirm the numbers.
2. Ask if there's something specific they'd like to explore — e.g. whether
   a different card would earn more, or what benefits they're missing.
3. If they want to explore alternatives or compare cards, call
   @tool.get_available_cards to see what the bank offers, then call
   @tool.get_card_details for whichever card they're interested in.
4. If they want a rewards comparison on a specific card, call
   @tool.get_card_details for that card first, then
   @tool.calculate_rewards_projection — it uses their actual spending
   pattern to project annual rewards on the target card.
5. Answer follow-up questions using data already fetched or by making
   additional tool calls.
6. Call @tool.complete in the same turn when advising is done or the
   conversation moves on. That includes when they ask you to perform an
   action this skill cannot do (product change, upgrade, switch, or
   application) — decline honestly, then complete — or when they return
   to another task. Complete this skill before starting or continuing
   another task.
