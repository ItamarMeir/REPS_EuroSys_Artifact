---
name: thesis-sync
description: Publish interactive experiment plots to the private thesis repo via sync_from_sim.ps1.
disable-model-invocation: true
---

Companion repo: [`ItamarMeir/Thesis_Itamar_BGU_Networking`](https://github.com/ItamarMeir/Thesis_Itamar_BGU_Networking) (private), local clone `C:\git_repos\Thesis_Itamar_BGU_Networking`. **Output-only**: thesis-facing interactive plots (self-contained `.html`) from exp28 onward and the 2026-10-06 meeting items, in its `REPS Buffer/` folder. No simulator code, no raw data.

- **This repo stays the source of truth.** One-way flow: regenerate plots here, commit here, then run `.\sync_from_sim.ps1` in the thesis repo. It copies them, packs each page's `DATA` blob (gzip+base64 inside the same `.html`, ~15x smaller), and rewrites its `SOURCES.md` with this repo's commit hash.
- Only touch the thesis repo when the user asks (e.g. "publish to the thesis repo", "sync the plots"). Never hand-edit its `REPS Buffer/` files or `SOURCES.md`.
- Sync from a clean tree (the script refuses a dirty tree without `-Force`). Commit here first so the hash in `SOURCES.md` reproduces the plots.
- New experiment page: add a row to the `$map` in the thesis repo's `sync_from_sim.ps1`.
- One repo per session (cwd = that repo); add the other via `/add-dir` only for the sync.
- `.gitignore` here ignores `experiments/**/*.html`, so interactive pages never reach this repo's remote; the thesis repo is where they are published.
