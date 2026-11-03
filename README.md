## GoGreen Studio 👀

A contribution-graph atelier for GitHub. GoGreen paints the 7 × 53 contribution
calendar with organic heatmaps, pixel art, lettering, gradients, waves, ripples
and constellations — then previews the result before creating anything.

**Made by Albatany 2026.**

## Quick start

Requirements:

- Python 3.8 or newer
- Git
- A GitHub personal access token with `repo` scope (classic token)

Optional: Pillow for JPEG, GIF, WebP and interlaced PNG imports. Plain PNG works
without it.

```bash
python3 git_backdate.py
```

On Windows:

```powershell
py git_backdate.py
```

You can also supply the token through the environment instead of typing it:

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxx
python3 git_backdate.py
```

The token is never written to `.git/config`. GoGreen always stores the clean
HTTPS remote and passes the authenticated URL only to the Git commands that need
it.

## Modes

| # | Mode | What it does |
|---|------|--------------|
| 1 | Random Scatter | Organic bursts, quieter weekends, natural-looking heat |
| 2 | Full Block | A solid slab of green at a chosen commits-per-day |
| 3 | Even Distribution | Splits a target total as evenly as possible |
| 4 | Pixel Art Studio | 12 built-in designs, custom 7-row matrices, image import |
| 5 | Text Banner | 5 × 7 lettering for A–Z, 0–9 and punctuation |
| 6 | Streak Builder | Controlled runs of consecutive green days |
| 7 | Gradient / Fade | Light-to-dark, dark-to-light, or a centre bloom |
| 8 | Wave / Pulse | Rhythmic bands with quiet troughs |
| 9 | Ripple | Concentric rings radiating from the centre |
| 10 | Constellation | Mirrored or kaleidoscope star fields |

### Pixel Art Studio

- **12 templates:** Heart, Invader, Ghost, Cat, Mushroom, Star, Diamond, Skull,
  Check, Smile, Flower and Sword.
- **Custom matrix:** paste seven rows using `0`–`4`, `.`, `+`, `*` or `#`.
- **Image import:** plain PNG uses the built-in decoder; install Pillow for other
  formats.
- **Styles:** Classic, Mono, Outline and Glow.
- **Placement:** centre, left, right or an exact column.
- **Windows:** rolling 52 complete weeks, rolling 53 weeks, a calendar year, or a
  custom Sunday start.

Text banners accept up to nine characters on the full 53-week canvas.

## What happens when you paint

1. GoGreen checks the repository, token, branch, permissions, fork/archive
   status, dirty working tree and divergence from the remote.
2. It shows a colour preview and a summary: dates, active days, commits per day
   and the rollback point.
3. After confirmation it writes real empty commits with backdated author and
   committer timestamps, using `git fast-import` for speed.
4. Pushes are sent in batches of at most 900 commits. This avoids GitHub
   silently ignoring contributions beyond the per-push counting limit.
5. The final commit and a local rollback hash are printed.

Every run has a rollback point:

```bash
git reset --hard <hash>
```

To undo the pushed history as well, force-push the branch (only after you are
sure):

```bash
git push --force origin <branch>
```

## Contribution graph notes

- Commits count only when the author email is verified on your GitHub account.
- Commits normally count on the default branch or a project's `gh-pages` branch.
- For private repositories, enable **Include private contributions** in your
  profile settings if you want visitors to see the art.
- Commits in a fork do not count toward your graph until they are merged into the
  parent repository (or the fork qualifies independently).
- GitHub shades cells relative to your busiest day in the displayed year. GoGreen
  calibrates four distinct shades against that maximum, but the exact GitHub
  algorithm is not public, so the preview is an approximation.
- Future dates stay empty until the day arrives. A rolling window can include the
  current week; the tool warns you when it does.
- Graph refreshes can take a few minutes, occasionally up to 24 hours.
- Very large runs can take a long time and may hit GitHub rate limits. The tool
  warns before big batches, but always test with a small range first.
