# CRDs

None. The Vault Agent Injector is a mutating admission webhook (installed with the Vault chart, see
[../../charts/vault/values.yaml](../../charts/vault/values.yaml)), so it reads plain pod annotations and
needs no custom resources. The minikube ingress addon brings its own controller.
