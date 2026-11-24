---
name: SIM Management
description: >
  Handle a lost or stolen SIM card or mobile device. Block the SIM, help the
  customer explore replacement options (physical SIM vs eSIM), order a
  replacement, and provide device info (IMEI) for police or insurance.
complete_when:
  condition: >
    session.sim_management.replacement_ordered == True
    or session.sim_management.replacement_declined == True
tool_constraints:
- block_sim:
    on_success: utter_sim_blocked
- order_replacement_sim:
    requires: session.sim_management.sim_type
    requires_confirmation:
      enabled: true
      utter_for_confirmation: utter_confirm_sim_order
      utter_on_user_denial: utter_sim_order_cancelled
    on_success: utter_sim_order_replacement_success
    on_failure: utter_sim_order_replacement_failed
- get_device_info:
    on_success: utter_device_info_shared
- get_device_recovery_status:
    requires: session.sim_management.incident_reason == 'lost'
utter:
- utter_sim_incident_advice:
    when: session.sim_management.incident_reason
---

Always call tools to get data — never invent IMEI numbers, confirmation
numbers, or device details.

Incident (lost vs stolen) and blocking may happen in either order.
Before replacement exploration, both must be done: the reason is
known, the matching advice has been given, and blocking is handled.

## Suspected SIM swap

If the customer still has the phone and the number may have moved to
another SIM, or they ask to secure the account against that:
1. Record the incident as stolen. Do not ask whether the phone was lost.
2. Block the SIM. Do not speak the IMEI or serial before the block.
3. Do not order a replacement unless they ask for one.

## Incident

1. Determine whether the device/SIM was lost or stolen. If that
   information was already provided, do not re-ask — continue with the
   next steps.
2. Recording incident_reason automatically gives the matching advice.
   Do not repeat advice already given for the current reason. If the
   reason changes, give the new advice once.

if: session.sim_management.incident_reason == 'stolen'
3. Do not invent IMEI or serial numbers — they are spoken only after
   @block.block_sim_flow finishes.

if: session.sim_management.incident_reason == 'lost'
3. Call @tool.get_device_recovery_status only if they ask whether Find My
   is currently enabled.

4. Once the advice has been given, move to blocking the SIM or getting
   device info based on what the user originally wanted.

## Block the SIM

To block the SIM, invoke @block.block_sim_flow and remain in that block
until it completes. It checks the SIM status, obtains consent, blocks the
SIM, and shares the device IMEI and serial. Do not begin replacement
exploration before the block completes.

1. Invoke @block.block_sim_flow and stay in it until blocking is finished,
   unless the customer cancels. The block checks the SIM status, asks for
   consent, blocks the SIM when the customer agrees, and then shares the
   IMEI and serial already on file. Do not invent those details. Blocking the
   SIM is possible only through @block.block_sim_flow.
2. After handling blocking, continue to Replacement exploration. Do not
   complete this skill before asking whether the customer wants a replacement.
   The customer may decline if they only want the SIM blocked.

:::ordered_block id=block_sim_flow
steps:
- id: check_status
  execute_tool: check_sim_status
  next: gate_status

- id: gate_status
  noop: true
  next:
  - if: session.sim_management.sim_blocked
    then: already_blocked
  - else: ask_block

- id: already_blocked
  noop: true
  next: device_info_gate

- id: ask_block
  collect: wants_to_block
  utterance: utter_ask_block_sim
  description: The customer's consent to block the SIM. Do not infer it from other statements.
  ask_before_filling: true
  next: gate_block

- id: gate_block
  noop: true
  next:
  - if: session.sim_management.wants_to_block == False
    then: left_active
  - else: do_block

- id: left_active
  utter: utter_sim_left_active
  next: END

- id: do_block
  execute_tool: block_sim
  next: device_info_gate

- id: device_info_gate
  noop: true
  next:
  - if: session.sim_management.device_info_shared or session.project.sim_device_info_shared
    then: END
  - else: share_device_info

- id: share_device_info
  execute_tool: get_device_info
  next: END
:::

## Replacement exploration

Do not start this section until the incident reason is known, the matching
advice has been given, and blocking is handled. If that advice has not
been given yet, give it first, then continue.

if: session.sim_management.incident_reason == 'lost' or session.sim_management.incident_reason == 'stolen'
1. Help the customer decide on a replacement. The two options are:
   - Physical nano-SIM card: shipped to their address, 2–3 business days,
     activates automatically when inserted.
   - eSIM (QR code): delivered instantly via email, scan to activate,
     requires Wi-Fi, not all devices support it.
2. If the customer asks about eSIM compatibility, call
   @tool.get_device_info to check.
3. Handle the customer going back and forth — changing their mind, asking
   about tradeoffs (traveling, switching phones, data roaming).
4. Ask which replacement they want, and set sim_type only after they
   name it. Currently sim type is @memory.sim_management.sim_type.
   Call @tool.order_replacement_sim only after that choice. The customer
   must clearly state which SIM type they want. Do not ask "shall I go
   ahead", "should I place the order", or any other confirmation
   yourself. Calling @tool.order_replacement_sim is the confirmation:
   the engine asks "Shall I go ahead?" and places the order only after
   the customer agrees. Call the tool once for the type they named, and
   do not call it again until they ask for a different SIM type.
   If they want the other type as well, set sim_type to that type and
   call @tool.order_replacement_sim once. Leave the earlier order in
   place unless they ask you to cancel it. Speak the new order ID.
5. If they don't want a replacement now, that's fine. Confirm that the
   SIM is blocked and that no replacement has been ordered, and set
   replacement_declined to true. If device info has not been given yet,
   go to Device info first.

if: session.project.sim_orders
Replacements already ordered in this conversation: @memory.project.sim_orders.
Do not order the same SIM type again. If they ask for another one "just in
case", say it is already ordered and repeat that order's ID.

## Device info

if: not session.sim_management.device_info_shared and not session.project.sim_device_info_shared
1. Invoke @block.deliver_device_info. Do not invent IMEI or serial, and do not
   only offer to share them later — the customer must hear the values from the
   tool utterance.

if: session.sim_management.device_info_shared or session.project.sim_device_info_shared
1. Do not call get_device_info again or invent identifiers.
2. After providing the device information, resume the unfinished part of SIM
   management that the customer interrupted: incident handling, blocking, or
   replacement exploration. Ask the next relevant question instead of silently
   listening, and complete this skill once the replacement is settled.

:::ordered_block id=deliver_device_info
steps:
- id: device_info_gate
  noop: true
  next:
  - if: session.sim_management.device_info_shared or session.project.sim_device_info_shared
    then: END
  - else: fetch_device_info

- id: fetch_device_info
  execute_tool: get_device_info
  next: END
:::
