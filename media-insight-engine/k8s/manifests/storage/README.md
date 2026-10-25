# Storage

Nothing to apply here. Postgres gets its volume from the `volumeClaimTemplates` in
[../deployments/postgres.yaml](../deployments/postgres.yaml) (one PVC, `data-postgres-0`), on minikube's
default `standard` StorageClass (hostPath). Overlays set the size.

The PVC outlives `kubectl delete -k`. To start from an empty database:
`kubectl -n mie-dev delete pvc data-postgres-0`.

On EKS, the same claim lands on the cluster's default StorageClass (gp3 via the EBS CSI driver).
