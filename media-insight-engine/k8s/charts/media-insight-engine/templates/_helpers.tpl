{{- define "mie.name" -}}
{{- .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* <release>-media-insight-engine, or just <release> when it already contains the chart name */}}
{{- define "mie.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "mie.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
app.kubernetes.io/name: {{ include "mie.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | trunc 63 | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: media-insight-engine
{{- end -}}

{{/* usage: include "mie.selector" (list . "server") */}}
{{- define "mie.selector" -}}
{{- $ := index . 0 -}}
app.kubernetes.io/name: {{ include "mie.name" $ }}
app.kubernetes.io/instance: {{ $.Release.Name }}
app.kubernetes.io/component: {{ index . 1 }}
{{- end -}}

{{/* usage: include "mie.image" (list . .Values.server.image) */}}
{{- define "mie.image" -}}
{{- $ := index . 0 -}}{{- $img := index . 1 -}}
{{- printf "%s:%s" $img.repository (default $.Chart.AppVersion $img.tag) -}}
{{- end -}}

{{/* Fail early on setups that would only break at runtime */}}
{{- define "mie.validate" -}}
{{- $ns := printf "mie-%s" .Values.env -}}
{{- if ne .Release.Namespace $ns -}}
{{- fail (printf "env=%s needs namespace %s (the Vault roles are bound to it): helm install ... -n %s --create-namespace" .Values.env $ns $ns) -}}
{{- end -}}
{{- if not (.Files.Glob "files/config/collections/*") -}}
{{- fail "files/ is empty: run scripts/chart-files.sh before installing from source (released charts include it)" -}}
{{- end -}}
{{- end -}}
