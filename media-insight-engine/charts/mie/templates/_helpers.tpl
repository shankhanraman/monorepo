{{/*
Chart name / release helpers.

NOTE: three Service names are LOAD-BEARING and must be literal within the namespace,
so they are NOT templated:
  - "db"     — matches the server cert SAN (DNS:db); sslmode=verify-full checks it.
  - "server" — client/nginx.conf hard-codes proxy_pass http://server:8003/.
  - "vault"  — VAULT_ADDR=http://vault:8200 in the app + cert-init.
Only the externally-reachable client Service is release-prefixed.
*/}}

{{- define "mie.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "mie.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "mie.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "mie.labels" -}}
app.kubernetes.io/name: {{ include "mie.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{/* Fully-qualified image reference: registry/repository:tag (registry optional). */}}
{{- define "mie.image" -}}
{{- $reg := .root.Values.images.registry -}}
{{- if $reg -}}
{{- printf "%s/%s:%s" $reg .repo.repository .repo.tag -}}
{{- else -}}
{{- printf "%s:%s" .repo.repository .repo.tag -}}
{{- end -}}
{{- end -}}
