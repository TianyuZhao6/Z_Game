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
- Timed browser wave renewals were still spawning a whole weighted wave at once. Even after batching that work, the first renewed enemy set could push Chrome over the edge once special enemy types and the wider web render path combined.
- A later audio regression left browser BGM on native HTML audio but kept comet/teleport skill SFX on the pygame mixer, so the first web skill SFX could still force mixer work mid-combat and bring back crackle or instability.

## Fixes Applied

- Added automatic obstacle-cache invalidation to the runtime obstacle map, so direct obstacle adds/removals now bump the navigation/render revision used by browser wall caches.
- Expanded the browser diagnostic harness to cover normal level 1, level-1 checks for wind/mist/hell/stone, longer biome checks, and wind boss coverage.
- Added a diagnostic `--scenario` filter so targeted browser regressions can be re-run without repeating the full matrix.
- Reduced wind-biome browser render cost by skipping the duplicate hurricane range hint when the cached tornado surface already contains the wind zone.
- Disabled only the enemy-paint render layer during the web wind biome; gameplay paint state still updates, but wind no longer pays for both tornado visuals and paint-surface rendering on the browser path.
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
- Converted timed web renewals to a queued spawn plan so browser waves no longer spawn their whole payload in one frame.
- Cached the lite-render static background as one composed floor-plus-wall layer and added off-screen culling for dynamic drawables to cut the post-renew render spike without changing the camera view.
- Restricted explicit timed web waves to the lighter browser-safe enemy subset and serialized that route to one active enemy at a time, which removed the repeatable 20-40s Chrome stall while still allowing a full level clear.
- Reverted default web BGM back to the native HTML-audio route after a later regression had moved browser BGM onto the pygame mixer path again, which reintroduced audible crackle/noise under load.
- Removed the game-side JS interaction gate before `audio.play()`, so the web build now attempts background-music autoplay on its own instead of waiting for a click before even trying.
- Moved web comet/teleport skill SFX onto the same native HTML-audio path as browser BGM, with pooled effect audio instances instead of on-demand pygame mixer playback.

## Notes

- Biome/obstacle validation was run through headless Chrome against the rebuilt pygbag bundle:
  - Full matrix report: `build/diagnostics/biome_obstacle_wind/browser_runtime_diag_report.md`
  - Final focused wind report: `build/diagnostics/wind_skip_paint/browser_runtime_diag_report.md`
- Full matrix coverage included `normal_level1`, `wind_level1`, `mist_level1`, `hell_level1`, `stone_level1`, longer wind/mist/hell/stone runs, menu transition, and wind boss.
- The full matrix reported `py_dead=False`, empty Python/JS error strings, and no transition stalls for the tested normal/biome runs. Obstacle counts did not show material late-session growth, which points away from the earlier invisible-obstacle symptom being live obstacle accumulation.
- Initial wind level-1 pacing was still rough: avg `50.73ms`, p95 `69.455ms`, with `r_hurricane_ms` and `r_paint_ms` as the major render costs.
- After the wind web-render changes, focused wind level-1 improved to avg `45.751ms`, p95 `61.305ms`; `r_hurricane_hint_ms` dropped from `8.271ms` to `0.006ms`, and `r_paint_ms` from `16.359ms` to `0.006ms`.
- Wind is improved but not perfect. The remaining hotspot is `r_hurricane_ms` itself, so further smoothing should target tornado surface size/rebuild cost rather than obstacle rendering.
- One automated repro that looked like a browser freeze was actually the fail/death screen, not a JS/Python crash.
- The most useful browser signals were `__zgame_py_frame`, `__zgame_py_heartbeat_ms`, `__zgame_prof_phase`, and whether Chrome showed a real dialog versus only a diagnostic error string.
- The autoplay popup and the long-run freeze were separate problems. The popup came from Chrome media policy. The browser dead-run issue showed up later with steady `py_frame`/heartbeat stalls and no matching JS exception.
- If autoplay still fails on a clean browser profile, that remaining block is the browser policy itself rather than a game-side interaction guard. The game code now attempts playback immediately and keeps retrying via the existing resume path.
- The most useful timed-wave repro was the explicit `?start=1&diag=1&timedspawns=1` route. Before the queued/safe-type fix it repeatedly stalled around the first renewal window; after the fix it stayed responsive through a level-complete screen in headless Chromium.
- Desktop gameplay is not affected by these web-only changes.
