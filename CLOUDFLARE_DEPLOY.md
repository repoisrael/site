# Cloudflare Pages deployment

Use these settings when connecting this repository to Cloudflare Pages.

## Project

Repository: `repoisrael/site`
Production branch: `main`
Framework preset: `Vite`
Build command: `npm run build`
Build output directory: `dist`

## Required setup

1. Open Cloudflare Dashboard.
2. Go to Workers & Pages.
3. Create application.
4. Choose Pages.
5. Connect to GitHub.
6. Select `repoisrael/site`.
7. Set production branch to `main`.
8. Set build command to `npm run build`.
9. Set build output directory to `dist`.
10. Deploy.

## Current repo-side preparation

- `package.json` has `build`, `test`, and `check` scripts.
- `wrangler.toml` points Pages output to `dist`.
- GitHub CI runs the build on `main`.
- Dependabot checks npm packages weekly.

## Important

Cloudflare account connection cannot be completed from GitHub alone. The repository is prepared, but Cloudflare must be authorized from the Cloudflare dashboard.
