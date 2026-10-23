# Standing project direction — updated 2026-10-23

- Work on the native/local desktop game only. Do not develop, build, test,
  optimize, or prepare browser versions unless the user explicitly changes this
  instruction. Existing browser support may remain; browser acceptance is not
  a requirement for finishing the desktop environment milestone.
- Ground-network palettes: Wind = cyan-blue; Forest = purple; Fire = red;
  Stone = pale gold to yellow. Stone uses the existing `Bastion of Stone` /
  `Mountain` identifiers internally. This decision supersedes older documents
  specifying cyan Region 04, jade Forest, or coral Fire.
- The approved starting point for the next refinement is `region04-shimmer`,
  produced by checkpoint `5184282`. Preserve its geometry and rendering until
  the user requests the next specific refinement. Preserve deterministic seeds,
  obstacle handling, world alignment, and cached illumination.
- Keep most branches subdued. Use brighter short connections near selected
  major junctions, tiny hot glint centers, and sparse soft halos. Illumination
  breathes asynchronously; geometry stays still. Avoid uniform neon or particles.
- Preserve gameplay, saved progress, approved walls/platform/background, and
  actors. Do not repeat completed work or discard existing local changes.
- Verify desktop visuals using actual rendered scenes and a full breathing
  cycle. Automated checks alone do not establish final visual acceptance.
- The user's selection of `5184282` supersedes the earlier `f195ad8` baseline
  and the later fine-branch candidate. Do not reapply those geometry changes
  or asset deletions. Keep the agreed four biome colors above.
