---
name: Card Replace
description: >
  Replace a customer's lost, stolen, damaged, or not-received credit or debit
  card. Checks account and card eligibility, routes by reason (stolen auto-lock,
  damaged scope check, lost/not-received fraud review), offers digital wallet
  provisioning, and ships a physical replacement. For a lost or not-received
  card, show the recent charges and record the verdict before locking. Place
  the replacement order in this chat after reason handling, wallet
  provisioning, and shipping are done. 
complete_when:
  condition: >
    session.card_replace.replacement_ordered == True
    or session.card_replace.account_eligible == False
    or session.card_replace.card_eligible == False
tool_constraints:
- check_account_eligibility:
    requires: session.card_replace.account_eligible == None
- check_card_eligibility:
    requires: session.card_replace.selected_card_id
- load_recent_transactions:
    requires: session.card_replace.card_eligible
- get_transaction_details:
    requires: session.card_replace.recent_transactions
- report_fraudulent_transactions:
    requires: session.card_replace.transaction_review_complete
- check_damaged_replacement_scope:
    requires: >
      session.card_replace.replacement_reason == 'damaged'
      and session.card_replace.card_eligible
- lock_card:
    requires: >
      session.card_replace.replacement_reason == 'stolen'
      or (
        (session.card_replace.replacement_reason == 'lost'
         or session.card_replace.replacement_reason == 'not_received')
        and session.card_replace.wants_card_locked
        and session.card_replace.transactions_look_familiar != None
      )
    on_success: utter_card_locked
- check_wallet_eligibility_and_status:
    requires: session.card_replace.card_eligible
- provision_digital_wallet:
    requires: session.card_replace.wallet_eligible
- check_rush_shipping_eligibility:
    requires: >
      session.card_replace.card_eligible
      and session.card_replace.wallet_eligible != None
- process_card_replacement:
    requires: >
      session.card_replace.card_eligible
      and session.card_replace.wallet_eligible != None
      and session.card_replace.shipping_type
      and session.card_replace.rush_eligible != None
      and not session.card_replace.replacement_ordered
      and (
        session.card_replace.replacement_reason == 'damaged'
        or session.card_replace.card_locked == True
        or (
          session.card_replace.wants_card_locked == False
          and session.card_replace.replacement_reason != 'stolen'
        )
      )
    requires_confirmation:
      enabled: true
      utter_for_confirmation: utter_confirm_order
      utter_on_user_denial: utter_order_cancelled
    on_success: utter_card_replace_complete

---

Never invent card details, transactions, or confirmation numbers — always
call the appropriate tool first. If the customer asks for something you are
not sure can be done in this chat, call search_knowledge before you answer
and follow the policy.

## Account eligibility

if: session.card_replace.account_eligible == None
1. Call @tool.check_account_eligibility.
2. If not eligible, inform the customer and end.
3. If eligible, acknowledge the customer's situation with empathy before
   proceeding.

## Collect reason and select card

if: session.card_replace.replacement_reason == None
1. Record the reason when it is already clear from what they said; only if it is
   still unclear whether the card is lost, stolen, damaged, or not received,
   ask once to confirm — then record it and do not ask again.

if: session.card_replace.replacement_reason != None
1. Current replacement reason is @memory.card_replace.replacement_reason.
   Do not ask again and do not change it unless the customer corrects it.

if: session.card_disambiguate.selected_card_id == None
2. Hand off to @skill.card_disambiguate to establish which card. Do not ask
   the customer which card yourself — @skill.card_disambiguate will use a card they
   already named and will only ask if it is unknown or ambiguous.
3. As soon as that skill returns, call @tool.adopt_selected_card so this skill
   records the chosen card. Then call @tool.check_card_eligibility.
   Do not offer to lock the card in this step.

if: session.card_replace.selected_card_id != None
2. If the customer corrects which card to replace:
   1. Keep the already-collected replacement_reason.
   2. Hand off to @skill.card_disambiguate (it uses the card they named
      without asking again), then call @tool.adopt_selected_card.
   3. Call @tool.check_card_eligibility for the new card.
   4. If not eligible, inform the customer and end.
   5. Finish replacement for the new card — re-do every step that depends on
      the selected card (reason handling, wallet, shipping, order). Do not
      reuse the previous card's information or answers.
   6. Do not order a replacement for the previous card after they switch.
   7. Actions already completed on the previous card stay completed.

if: session.card_replace.account_eligible == True and session.card_replace.selected_card_id != None and session.card_replace.card_eligible == None
Make sure this card is eligible before proceeding to the next steps. Call
@tool.check_card_eligibility.

## Handle reason

Do the reason step before the wallet, shipping, or the order. If the customer asks for a wallet first, do that, then return to the reason step.

if: session.card_replace.replacement_reason == 'stolen' and session.card_replace.card_eligible == True and session.card_replace.card_locked != True
1. Call @tool.lock_card immediately — do not ask the customer for consent first.
   When the reason is stolen, locking happens automatically — it does not
   depend on whether the customer wants the card locked. Do not set
   wants_card_locked or replace_target.

if: session.card_replace.replacement_reason == 'stolen' and session.card_replace.card_eligible == True and session.card_replace.card_locked == True
2. Tell the customer the card is locked.
3. Proceed to wallet provisioning — do this even when the customer sounds
   urgent or asks to skip straight to shipping. The wallet eligibility check
   must run before shipping can begin, regardless of urgency.

if: session.card_replace.replacement_reason == 'damaged' and session.card_replace.card_eligible == True
Locking the card is not allowed — even if the customer asks. Do not set
wants_card_locked. Call @tool.check_damaged_replacement_scope.

if: session.card_replace.replacement_reason == 'damaged' and session.card_replace.card_eligible == True and session.card_replace.has_authorized_users == True
1. Show the authorized users and ask who needs a replacement — the customer,
   the authorized user, or both.
2. Record with @tool.set_memory(replace_target=...).
3. Proceed to wallet provisioning.

if: session.card_replace.replacement_reason == 'damaged' and session.card_replace.card_eligible == True and session.card_replace.has_authorized_users == False
Proceed to wallet provisioning.

if: (session.card_replace.replacement_reason == 'lost' or session.card_replace.replacement_reason == 'not_received') and session.card_replace.card_eligible == True and session.card_replace.transaction_review_complete != True
1. Call @tool.load_recent_transactions in the same response — do not only
   say you will look up charges (a text-only promise ends the turn with no
   list).
2. Present the returned list once and ask if they all look familiar. If no
   transactions are returned, say so and do not invent a verdict.
3. If the customer asks about a specific charge, call
   @tool.get_transaction_details. Handle as many follow-ups as needed.
4. When they give their verdict, record it with
   @tool.set_memory(transactions_look_familiar=...). Do not infer that
   verdict from other answers. If any charges are unfamiliar, help identify
   which ones and call @tool.report_fraudulent_transactions once, passing
   every unfamiliar transaction id in transaction_ids. Share the report ID
   and the list of flagged transactions before moving on.
5. Do not bring up a lock, a wallet, or shipping in this step. If they ask to lock the card, set wants_card_locked to true and call @tool.lock_card only after the charges have been shown and they have said whether they look familiar.

if: (session.card_replace.replacement_reason == 'lost' or session.card_replace.replacement_reason == 'not_received') and session.card_replace.card_eligible == True and session.card_replace.transaction_review_complete == True
If the customer asks about a specific charge, call
@tool.get_transaction_details and tell them the merchant, amount, or date,
then return to the unfinished step.
That question is not a dispute. Do not file a report, and do not change
transactions_look_familiar, unless they then say the charge was not theirs.
If the customer says a charge from the list was not theirs, including after
they already said the charges looked familiar:
1. Set transactions_look_familiar to false with @tool.set_memory.
2. Call @tool.report_fraudulent_transactions once, passing every disputed
   transaction id in transaction_ids.
3. Tell them the report id and which charges were flagged before moving on
   to the wallet, shipping, or the order.

if: (session.card_replace.replacement_reason == 'lost' or session.card_replace.replacement_reason == 'not_received') and session.card_replace.card_eligible == True and session.card_replace.transaction_review_complete == True and session.card_replace.card_locked != True and session.card_replace.wants_card_locked == None
1. Ask whether they want this card locked. Wait for that answer.
2. Do not infer consent from the charge review, a wallet request, or a
   shipping choice. Do not call @tool.lock_card or mention a wallet until
   they answer.
3. If they agree, set wants_card_locked to true.
4. If they decline, set wants_card_locked to false. Do not leave it unset.

if: (session.card_replace.replacement_reason == 'lost' or session.card_replace.replacement_reason == 'not_received') and session.card_replace.card_eligible == True and session.card_replace.transactions_look_familiar != None and session.card_replace.wants_card_locked == True and session.card_replace.card_locked != True
The user gave consent to lock this card (wants_card_locked : @memory.card_replace.wants_card_locked).
Make sure you lock the card, because it is not locked
(card_locked: @memory.card_replace.card_locked).
1. Call @tool.lock_card now. Do not ask for consent again.
2. Do not say the card is locked in this step. Do not place the order until
   lock_card has run.

if: (session.card_replace.replacement_reason == 'lost' or session.card_replace.replacement_reason == 'not_received') and session.card_replace.card_eligible == True and session.card_replace.transaction_review_complete == True and session.card_replace.card_locked == True
1. Tell the customer the card is locked.
2. Proceed to wallet provisioning.

if: (session.card_replace.replacement_reason == 'lost' or session.card_replace.replacement_reason == 'not_received') and session.card_replace.card_eligible == True and session.card_replace.transaction_review_complete == True and session.card_replace.wants_card_locked == False
1. Do not call @tool.lock_card.
2. Proceed to wallet provisioning.

## Wallet provisioning

Offer wallet provisioning after the reason-specific handling for the selected
card is done — run the wallet check and offer before shipping or placing the
order for that card. If the customer asks to set up a wallet earlier, honour
that request then — do not make them wait.

1. Call @tool.check_wallet_eligibility_and_status before mentioning a
   digital wallet. Do not ask about Apple Pay or Google Pay until that
   tool has returned for the selected card.
2. If not eligible or already provisioned, skip to shipping.
3. Ask if they'd like to add the new card to a digital wallet — Apple Pay
   or Google Pay. If they already asked for a named wallet, skip the ask —
   check eligibility and provision.
4. If they accept, call @tool.provision_digital_wallet. If they already
   named Apple Pay or Google Pay, use that. Only ask which if they said
   yes without naming one.
5. Proceed to shipping.

## Shipping

Current shipping preference is @memory.card_replace.shipping_type.
If they are not eligible for rush (current eligibility:
@memory.card_replace.rush_eligible), never record shipping_type as rush —
tell them and record standard. If they insist on rush, explain again
that they are not eligible.

if: session.card_replace.rush_eligible == None
Call @tool.check_rush_shipping_eligibility for the selected card before
talking about shipping speed or placing the order. Do not skip the check
because they already named standard or rush.

if: session.card_replace.shipping_type == None and session.card_replace.rush_eligible == False
Tell them they are not eligible for rush and record standard.

if: session.card_replace.shipping_type == None and session.card_replace.rush_eligible == True
Ask whether they want rush or standard shipping and record their choice. If they already named the shipping type they want, record it — do not ask.

if: session.card_replace.shipping_type != None and session.card_replace.rush_eligible != None
Shipping type is set to @memory.card_replace.shipping_type. Do not ask standard or rush again. An already-known shipping type does not skip the lock or the wallet offer. If the customer agreed to a lock and the card is not locked, call @tool.lock_card before anything else. Offer the digital wallet before placing the order. Do not offer the other speed yourself and do not ask them to keep the current speed
or switch. Change the preference only when they ask: rush to standard is always
allowed; standard to rush only when customer is eligible.

## Order

The replacement order happens at the end, after reason handling, wallet
provisioning, and shipping are done. If the wallet has not been offered yet, offer it before you place the order.

Call @tool.process_card_replacement only after reason handling, lock (if
the customer agreed or the card was stolen), wallet, and shipping_type
are done. Do not ask the customer to confirm the order — the tool does
that. This is the last step of the replacement: do not call it until
those earlier steps are done.

Once the order is confirmed, call @tool.complete.
