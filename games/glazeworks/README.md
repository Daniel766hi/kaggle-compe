# Glazeworks

An original block-placing puzzle in a single file with no dependencies. You place glazed tiles on an 8×8 kiln shelf, and every full row or column fires off the shelf.

The genre (grid plus line clears) is open to everyone. The name, art, code and the mechanics below are this project's own. It contains no code or assets from any other game.

## What makes it different

| Mechanic | How it works | Why it matters |
|---|---|---|
| **Pure lines** | A line cleared in one glaze colour scores ×3 (30 instead of 10) | Adds a colour-planning layer on top of the shape puzzle |
| **Kiln heat → turn tokens** | Pure lines and multi-line clears add heat. 3 heat earns a ↻ token (max 3). Tapping a tray tile spends one ↻ to rotate it 90° | Gives players an earned way out of a stuck hand |
| **Crackle** | 4 placements in a row with no clear drop a cracked shard on a random empty cell. Shards clear normally with their line but break purity | Steady pressure that punishes stalling |
| **Stitch pieces** | Diagonal 2- and 3-cell pieces | Shapes that the usual polyomino set lacks |
| **Daily Firing** | One seed per calendar day, numbered, with a copyable result | Built-in reason to come back daily and share scores |

Scoring: +1 per cell placed. Each cleared line is worth 10 (30 if pure) × lines cleared at once × streak multiplier (×1, ×1.5, ×2 … up to ×3 for consecutive clearing turns).

## Files

- `glazeworks.html`: the game (page body, used for the claude.ai Artifact)
- `build.sh`: wraps it into `index.html`, a full standalone page
- `index.html`: upload this anywhere

Run `./build.sh` after you edit `glazeworks.html`.

## Getting it in front of players

1. **itch.io** (free, 10 minutes): create an HTML project, zip `index.html`, upload it and tick "This file will be played in the browser". Good for feedback and a first audience.
2. **GitHub Pages** (free): enable Pages for the repo and the game is served at `https://<user>.github.io/<repo>/games/glazeworks/`.
3. **Web game portals: CrazyGames, Poki, GameDistribution.** These portals bring the traffic and split ad revenue with you. Each has its own SDK for ads and loading events, so you integrate it once the portal accepts you. This is usually the fastest route to real players for a web puzzle.
4. **Android / iOS**: wrap the page with Capacitor (or a Trusted Web Activity on Android), then add AdMob. Google Play costs $25 once, Apple $99/year.

## How it can earn

- **Rewarded ads**: the best fit is a **"Rekindle"** continue on the game-over screen (watch an ad → the shelf loses a few random tiles and you keep playing), or "watch an ad for a ↻ token". Players opt in, so it feels fair, and it pays better than banners.
- **Interstitials** between games, at most one every few minutes.
- **Cosmetic glaze packs** (raku, porcelain, neon) as a one-off purchase or "remove ads" in the app versions.

Be realistic: web ad revenue is small per player, roughly cents per player per session, so income depends on reach and retention. Ship a free version first, see whether people come back to Daily Firing, and only then put time into ads and app stores.

## Next steps before launch

- [ ] Add the "Rekindle" continue flow (game logic first, then plug in the ad SDK)
- [ ] Simple analytics: games started, average score, Day-1 return rate
- [ ] Have 5–10 people playtest. Tune crackle (4 turns) and the piece weights in `SHAPES`
- [ ] A short trailer/GIF of a pure-line clear for the store or portal page
