{{- define "obs.labels" -}}
app.kubernetes.io/part-of: ocr-lab
app.kubernetes.io/managed-by: {{ .Release.Service }}
release: {{ .Values.prometheusReleaseLabel }}
{{- end }}
