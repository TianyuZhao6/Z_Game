# Current visual evidence

The active desktop baseline is **region04-shimmer**, produced by checkpoint `5184282`. On 2026-10-23 the user selected this version over the later route and fine-branch revisions. The network runtime and matching validation tools have been restored to that checkpoint. Current colors remain Wind cyan-blue, Forest purple, Fire red, and Stone pale gold/yellow.

The `network-fine-branches` folder is a superseded experiment, retained for historical comparison only. It does not represent the current game.

The older **network-routes** evidence folder was removed during user cleanup. Only the latest review evidence has been recreated, as requested. Its before-images render the selected `f195ad8` baseline; the original tracked evidence remains recoverable from that checkpoint.

The selected palette/shimmer evidence:

- [Four biome palettes](region04-shimmer/biome-palettes.png)
- Stone: [dim](region04-shimmer/after-dim.png), [intermediate](region04-shimmer/after-rising.png), [peak](region04-shimmer/after-peak.png)
- [Full breathing cycle](region04-shimmer/breathing.webp) and [measured node pixels through time](region04-shimmer/breathing-metrics.json)
- [Paired desktop measurements](region04-shimmer/desktop-profile.json), [capture timing](region04-shimmer/capture-times.json)
- [Desktop shimmer validation](../region04-desktop-shimmer-validation.md)
- [Current desktop combat](region04-shimmer/live-combat.png) and [live validation](region04-shimmer/live-validation.json)
- Historical cyan Region 04: [peak](region04-palette/after-peak.png), [combat](region04-palette/live-combat.png), [live gameplay results](region04-palette/live-validation.json), [earlier report](../region04-palette-validation.md)

Only the selected central vessel group's phase determines the dim/intermediate/peak labels. Other groups remain asynchronous. The fixed-camera breathing clip preserves the actual animation timing.

Older performance JSON files remain for comparison. Superseded environment/network screenshots and videos were removed; historical reports are marked accordingly. Those tracked files can be recovered from checkpoint `0aa3e05`. The parallax pair and unrelated summon captures remain useful independent evidence.

TEMP is disposable test output, not a runtime asset source. Obsolete environment logs, intermediate captures, scratch review scripts, and empty browser-test directories were removed. `TEMP/savegame.json`, audio-analysis data, and unrelated summon test output were preserved. No Windows system temporary directory was cleaned. The [cleanup inventory](region04-palette/temp-cleanup.json) lists the measured generated files removed; nine small scratch scripts, three duplicate newly generated before-images, and empty directories were also removed.
