# meetings

Written plans derived from supervisor meetings. They record what was asked, what blocks it in the code, and how each request maps to an experiment in this repository. Results of the work are in the experiment directories, not here.

- [`2026-10-06_buffer_size_plan.md`](2026-10-06_buffer_size_plan.md) — plan from the 2026-10-06 meeting. The main blocker it records: freeze under partial degradation depends on the trim setting and an RTT gate (`_last_rto_max_rtt < 1.65 x _base_rtt`), so "run without trim" is not a free switch. It lists the action items (per-packet EV-source split, valid-EV count and slow-motion view, B up to 256, speed-of-light oracle, same Y axes, bursty traffic, an SLRU idea) and maps them to the items in [`../meeting_06_10_26/`](../meeting_06_10_26/).
