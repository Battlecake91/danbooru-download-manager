# Release Workflow

## Normal Push

Run the local preflight checks first:

```bash
python scripts/pre_push_check.py
```

Then commit and push as usual:

```bash
git add .
git commit -m "Describe the change"
git push origin master
```

Every push to `master` or `main` runs the Windows and Ubuntu test matrix in GitHub Actions.

## Manual Build Artifacts

Use the `Build Artifacts` workflow in GitHub Actions when you want test ZIPs without publishing a release.

It builds Windows and Ubuntu artifacts. Enable the `onefile` input to test the single-executable route.

## Published Release

Create and push a version tag:

```bash
git tag -a v1.3.195 -m "Release v1.3.195"
git push origin master
git push origin v1.3.195
```

Pushing a `v*` tag starts the `Release` workflow. It runs the test matrix, builds Windows and Ubuntu ZIPs in both portable and onefile modes, then uploads all ZIPs to the GitHub release.

The release workflow can also be started manually with a version input. Manual runs default to draft releases.

## Local Release Build

Portable folder-style build for the current platform:

```bash
python scripts/make_release.py --allow-dirty
```

Single-executable build for the current platform:

```bash
python scripts/make_release.py --allow-dirty --onefile
```

Local publishing through `scripts/make_release.py --tag --push --publish` remains available, but the tag-driven GitHub Actions workflow is the preferred release path because it builds both Windows and Linux artifacts.
