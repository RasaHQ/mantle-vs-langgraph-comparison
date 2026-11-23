---
name: Card Disambiguate
description: >
  Show the customer their cards and help them pick which one to act on.
tool_constraints:
- get_customer_cards:
    on_failure: utter_customer_cards_failed
---

Help the customer identify which card they want to act on.

1. Fetch cards — call @tool.get_customer_cards. Always call the tool; never
   invent card details.
2. If the customer has already named or described a card (by name, type, or
   last 4 digits), match it to the fetched card list yourself and record it:
   call @tool.set_memory(selected_card_id=...) with the matching card's ID
   from the list. Confirm briefly, then call @tool.complete so the
   caller resumes.
3. Only if the customer has not named a card, or you cannot confidently match
   it, or it is ambiguous, present the fetched cards clearly (label and type
   for each) and ask which one they want. Record the choice with
   @tool.set_memory(selected_card_id=...), then @tool.complete.
4. Never ask the customer to choose a card they have already unambiguously
   identified.
