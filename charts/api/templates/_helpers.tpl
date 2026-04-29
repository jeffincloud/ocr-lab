{{- define "ocr-api.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ocr-api.fullname" -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ocr-api.labels" -}}
app.kubernetes.io/name: {{ include "ocr-api.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "ocr-api.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ocr-api.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
