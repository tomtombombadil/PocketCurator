# Pocket Curator v0.61.13 (beta)

On-device ROM and scraped-media cleanup for retro handhelds. ROCKNIX + Knulli,
plus AmberELEC and ArkOS-family (incl. dArkOS / R36S).

## This build
- **dArkOS / ArkOS: the games-list refresh no longer freezes for ~90 seconds.**
  v0.61.12's refresh worked but could land its `systemctl stop` while ES was
  still suspended in its game-launch wait, where ES can't process SIGTERM -
  so systemd sat out its full 90s stop timeout before force-killing. The
  restart sequence now gives ES a 3s head start, watches the stop, and
  force-completes it after 5s if needed. Typical refresh: a few seconds;
  worst case ~8s.
- **Cleaner exit on ArkOS-family.** The black screen with `^]`-style garbage
  between the app closing and the "Refreshing your games list..." message is
  now reset, and Pocket Curator's own `Killed` process notices no longer
  print over the console. (Two similar notices from PortMaster's own
  pm_finish are outside our tree and may still flash.)
- ROCKNIX, Knulli, Batocera, and AmberELEC behavior is unchanged from
  v0.61.12.

## Upgrade note
Drop-in replacement for v0.61.12; only `Pocket Curator.sh` and the version
stamp changed.
