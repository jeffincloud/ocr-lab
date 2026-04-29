{{- define "ocr-frontend.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ocr-frontend.fullname" -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ocr-frontend.labels" -}}
app.kubernetes.io/name: {{ include "ocr-frontend.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "ocr-frontend.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ocr-frontend.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
