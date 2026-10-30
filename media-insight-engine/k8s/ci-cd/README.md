# CI/CD → Kubernetes

**CI and image builds** already run in GitHub Actions:
[.github/workflows/media-insight-engine.yml](../../../.github/workflows/media-insight-engine.yml).
Every merge to `main` that passes the tests publishes:

- `ghcr.io/shankhanraman/mie-server:<commit-sha>` and `:latest`
- `ghcr.io/shankhanraman/mie-client:<commit-sha>` and `:latest` (production nginx build)

**Deploying** is a manual promotion, because the cluster is a local minikube that GitHub's runners can't
reach:

1. Pick the commit SHA of a green run on `main` (`gh run list --workflow media-insight-engine.yml`).
2. Set it as `newTag` for both images in `overlays/test/kustomization.yaml`, then deploy:
   `GHCR_TOKEN=<PAT with read:packages> scripts/deploy.sh test`
3. Once it's good in test, set the same SHA in `overlays/prod/kustomization.yaml` and run `scripts/deploy.sh prod`.

Pinning a SHA, never `latest`, means each overlay records exactly what runs, and rolling back is a one-line
revert.

**On EKS later:** the same overlays work. Automate step 2 with Argo CD or Flux watching this folder (GitOps),
or add a deploy job to the workflow once the cluster is reachable from Actions (OIDC to AWS, no stored keys).

## The Helm chart
[.github/workflows/helm-release.yml](../../../.github/workflows/helm-release.yml) publishes
`charts/media-insight-engine` when a push to `main` changes it. It uses chart-releaser: one GitHub Release per
chart version, plus `index.yaml` on the `gh-pages` branch, served at https://shankhanraman.github.io/monorepo.

To release: change the chart, **bump `version` in Chart.yaml** (and `appVersion` to a new image SHA if the images
changed), and merge. A version that already exists is skipped. The PR workflow's `k8s` job lints the chart and
renders the chart and the Kustomize overlays for every environment.
