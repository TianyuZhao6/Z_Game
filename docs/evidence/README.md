# Current visual evidence

The active Region 04 network review is **region04-palette**. These are real desktop renderer captures, not concept artwork.

- [Previous palette, peak](region04-illumination/after-peak.png)
- New palette: [dim](region04-palette/after-dim.png), [intermediate](region04-palette/after-rising.png), [peak](region04-palette/after-peak.png)
- [Eight-second asynchronous breathing](region04-palette/breathing.webp)
- [Live combat](region04-palette/live-combat.png) and [camera movement](region04-palette/live-camera.webp)
- [Paired desktop measurements](region04-palette/desktop-profile.json), [live gameplay results](region04-palette/live-validation.json), [capture timing](region04-palette/capture-times.json)
- [Palette implementation and validation](../region04-palette-validation.md)

Only the selected central vessel group's phase determines the dim/intermediate/peak labels. Other groups remain asynchronous. The live-camera clip is condensed gameplay; the fixed-camera breathing clip preserves the actual animation timing.

Older performance JSON files remain for comparison. Superseded environment/network screenshots and videos were removed; historical reports are marked accordingly. Those tracked files can be recovered from checkpoint `0aa3e05`. The parallax pair and unrelated summon captures remain useful independent evidence.

TEMP is disposable test output, not a runtime asset source. Obsolete environment logs, intermediate captures, scratch review scripts, and empty browser-test directories were removed. `TEMP/savegame.json`, audio-analysis data, and unrelated summon test output were preserved. No Windows system temporary directory was cleaned. The [cleanup inventory](region04-palette/temp-cleanup.json) lists the measured generated files removed; nine small scratch scripts, three duplicate newly generated before-images, and empty directories were also removed.
