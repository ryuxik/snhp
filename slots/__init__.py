"""SLOT-ECONOMICS — one world core, three venue calibrations.

The inventory is TIME: a venue is capacity units (chairs / spaces / seats)
crossed with a day of 10-minute ticks, and an unsold unit-tick perishes
worthless. Three arms price it: the posted list (static/1), an hourly
inventory-vs-demand re-price (computed/1), and a per-arrival Nash quote
over slot-shift x duration x price (nego/1). Pure math — no LLM calls
anywhere in this package.
"""
