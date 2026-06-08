# Pocket Curator v0.61.9 (beta)

On-device ROM and scraped-media cleanup for retro handhelds. ROCKNIX + Knulli.

## This build
- **Reverted the ROCKNIX A/B change from v0.61.8.** That swap was wrong - it
  would have reversed buttons on correctly-configured ROCKNIX devices. ROCKNIX
  buttons are back to the original mapping.
- **Added a controller diagnostic** to the launch log: it prints the SDL
  face-button mapping and input device names gptokeyb is using, so a misbehaving
  unit can be compared against a working one.
- Keeps the v0.61.8 logo fix (Pulse and other themes that store logos in `art/`
  now resolve correctly).

## Investigating reversed A/B on a single device
If A/B feel swapped in ports/Pocket Curator on one device but are fine in
EmulationStation, ES and gptokeyb are reading different controller mappings.
Launch Pocket Curator on the affected unit and on a working unit, then compare
the `--- controller diag ---` block in each `pocketcurator.log` (the `a:`/`b:`
lines). A difference there is the cause.
