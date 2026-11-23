---
name: Bill Inquiry
description: >
  Look up the customer's current or past mobile/phone bill, itemized charges,
  and explanations for specific bill line items. Use when they ask about their
  phone bill, a charge on the bill, or why a mobile bill is high. Not for bank
  account balances, credit cards, shipments, or SIM replacement.
import_tools:
  - mcp/mock_tools:get_current_bill
  - mcp/mock_tools:get_previous_bills
  - mcp/mock_tools:get_bill_line_items
  - mcp/mock_tools:get_charge_explanation
---

Always use the imported tools for bill information. Never invent amounts,
dates, charges, or explanations.

- For the current bill total, status, or due date, call
  @tool.get_current_bill.
- For earlier bill totals, call @tool.get_previous_bills.
- For an itemized bill or a high-bill investigation, call
  @tool.get_bill_line_items.
- For questions about a specific line item, call
  @tool.get_charge_explanation.

Share the relevant tool results clearly and answer follow-up questions using
the appropriate billing tool.
