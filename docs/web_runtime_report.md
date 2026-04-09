# Web Runtime Report

## Symptoms

- Browser combat felt progressively worse in longer sessions and often looked "dead" after extended play.
- Combat BGM started late on the web build, or stayed on the intro track.
- Chrome autoplay rejection showed up like a runtime error even when the game itself was still alive.

## Root Causes

- The browser build had a hard `single_bgm` override in the web quality payload, so combat could stay pinned to the intro music.
- Web gameplay still had an explicit `0.75s` combat-BGM delay after entering a level.
- Browser autoplay `play()` promise failures were being recorded as hard errors, which made diagnostics look like a crash.
- Chrome also reported a non-game startup resource event from the blocked `browserfs.min.js` fetch, which showed up as `error: [object Event]` in diagnostics.
- The browser enemy path was still doing heavy desktop-style movement/state work, including obstacle mutation, which made long browser sessions unstable.
- Web gameplay rendering was also accidentally staying on the hot path more often than intended because the browser loop used a `last_frame is None` gate even when the web renderer intentionally returned `None` with `copy_frame=False`.
- Browser enemy projectiles are still unstable in wasm long-run sessions. Repros consistently stopped once enemy-shot processing became active, even when JS and Python error flags stayed empty.

## Fixes Applied

- Removed the forced `single_bgm` behavior from the web quality payload so combat can switch to `ZGAME.ogg`.
- Removed the extra combat-BGM startup delay on web.
- Ignored known autoplay rejection strings in the browser error recorder so non-fatal audio policy failures do not appear as engine crashes.
- Ignored the known `browserfs.min.js` startup load event so it no longer surfaces as a fake runtime error on Chrome.
- Kept combat music on the normal `ZGAME.ogg` path and switched it with zero web fade delay.
- Moved normal web enemies onto a simpler browser-only chase/collision path instead of the full desktop movement stack.
- Stopped browser fallback enemies from chewing through map obstacles during chase updates, which keeps the web obstacle layout stable and removes a browser-only state churn source.
- Added a cached web wall layer for the lite isometric renderer so the web path no longer rebuilds the wall field every draw.
- Split the web render throttle from `last_frame`, so `copy_frame=False` no longer forces full-rate redraws.
- Limited browser enemy-shot volume, optimized enemy-shot obstacle lookup to nearby cells, and added a hidden opt-in flag for restoring web enemy projectiles when debugging.
- Switched the default browser route onto the safer `WEB_SKIP_ENEMY_SHOTS` path so normal `8765` play is not blocked by the projectile freeze.
- Reused the already-armed intro/home BGM session instead of forcing a fresh intro load, so intro and homepage stay on the same music path.

## Notes

- One automated repro that looked like a browser freeze was actually the fail/death screen, not a JS/Python crash.
- The most useful browser signals were `__zgame_py_frame`, `__zgame_py_heartbeat_ms`, `__zgame_prof_phase`, and whether Chrome showed a real dialog versus only a diagnostic error string.
- The autoplay popup and the long-run freeze were separate problems. The popup came from Chrome media policy. The browser dead-run issue showed up later with steady `py_frame`/heartbeat stalls and no matching JS exception.
- Desktop gameplay is not affected by these web-only changes.
