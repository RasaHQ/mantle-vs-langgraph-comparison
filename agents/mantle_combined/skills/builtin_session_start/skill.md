---
name: Session Start
description: Greet the user at the start of a session.
routing:
  engine_managed: true
---

:::ordered_block id=main
name: builtin_session_start
steps:
  - id: greet
    utter: utter_greet
:::
