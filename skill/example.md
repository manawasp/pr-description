# Worked example

narset-io/narset#471, 22 files, +1979/−330. The original body was 821 words of
rationale under the same three headings as every other PR. This is the same PR
in the template and the neutral voice. The guard accepts it.

---

## Why
The app origin sent no security headers, while the landing build on the same origin has carried a strict CSP since #257. An XSS on either could call `/api` with the visitor's session.
Closes #423.

## What changed
- Every response from the h3 server now carries CSP, HSTS, `nosniff`, Referrer-Policy, X-Frame-Options and Permissions-Policy, proxied `/api` included.
- Socket and storage origins come from the variables the bundle and backend already use. A missing variable narrows the directive to `'self'`.
- `CSP_MODE=report-only` sends the report-only header and mounts a collector that logs each violation to stdout.
- The build fails when `dist/` contains an inline script or an icon is not bundled.
- The entrypoint is separated from the app so the integration test can start it.

## How to verify
- Lint, typecheck and 612 unit tests pass in `src/frontend`.
- `pnpm build` passes, and the dist check fails on an injected inline script.
- Smoke test in both modes: headers on the shell, an asset and a 404. The collector logs a violation and answers 204.
- E2E not run locally with the backend down. CI runs it.

## Notes for the reviewer
- `frame-src https:` and `https:` on `img-src` and `media-src` are wider than the issue specified. The embed block and every media block's Link tab load arbitrary URLs, so a narrower directive would blank existing content. #439 covers the allowlist.
- `style-src` keeps `'unsafe-inline'` because Tailwind and Vue `:style` bindings write inline styles.

<details><summary>Files</summary>

| File | Change |
|---|---|
| `src/frontend/server/security-headers.ts` | Added a pure builder that turns the config into a header map. One middleware applies the map to every route, including routes added later. |
| `src/frontend/server/app.ts`, `server/index.ts` | Moved the app into `app.ts` and reduced `index.ts` to binding the port, so the integration test can start the real app on its own port. Proxied responses get the headers re-applied in `onResponse`, because h3 copies upstream headers as they are. |
| `src/frontend/server/csp-report.ts` | Added the report-only collector. It caps the body at 16 KB as bytes arrive, shares the proxy's rate-limit budget, truncates every field and answers 204 in every case. It is mounted when `CSP_MODE=report-only`. |
| `src/frontend/server/client-ip.ts` | Added `requestIsHttps`, which reads `x-forwarded-proto` with the same trusted-hop count as `resolveClientIp`. HSTS is set when the socket or a trusted hop reports TLS. |
| `src/frontend/server/__tests__/*.spec.ts` | Added five spec files: the header builder, HSTS resolution, the enforced and report-only apps end to end, and the collector's caps. |
| `src/frontend/scripts/verify-dist.mjs` | Added a post-build check that fails when `dist/` contains an inline script, since `script-src 'self'` blocks inline scripts. Run by `pnpm build`. |
| `src/frontend/scripts/icons.mjs`, `vite.config.ts` | Added a scan that bundles every icon used in `app/` and `libs/runes`, because an icon that is not bundled is fetched at runtime and `connect-src` blocks the request. A missing icon collection fails the build with the icon name. |
| `e2e/app-browser/playwright.config.ts`, `.github/workflows/e2e-tests.yml`, `src/frontend/Dockerfile.prod` | Pass `VITE_WS_URL` and `PUBLIC_S3_ENDPOINT` to the h3 server so the policy allows the realtime socket and uploads. |
| `e2e/app-browser/test/editor/upload.spec.ts` | Added a real upload that asserts the console carried no CSP violation. |
| `src/frontend/package.json`, `pnpm-lock.yaml` | Added the icon collections the scan installs. |
| `docs/specs/LANDING.md`, `CLAUDE.md`, `src/tauri/README.md` | Recorded the decision in §5.3, the environment variables and an "App-origin security headers" section, and why `frame-ancestors 'none'` does not affect the Tauri window. |
</details>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
