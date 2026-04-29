# Where we paused — 2026-04-26

## Status
- ✅ Outline completo en `outline.md`
- ✅ Visuales capturados en `visuals/` (12 archivos: tree, kernel-pin, cluster-ready, mermaid arch, 7 screenshots de frontend, error CUDA 804)
- ✅ Template CNCG subido a Claude Design
- ✅ Form de Claude Design completado con respuestas en español + 4 war stories + stack + takeaway
- ✅ **Primer draft generado** — `slides-v1.html` (Claude Design output)
- ⏸ **PAUSADO ANTES DE:** revisar/corregir alucinaciones del draft, generar bloques 2-6

## Decisiones tomadas en Claude Design form
- Idioma: Español
- ~36 slides para 60 min
- Estructura: 4 secciones (Why / What / How / Lessons)
- Demo en vivo con slide de transición
- Sí, slide final con QR/recursos
- Honestidad: Balanceado (funciona pero con caveats)

## Hallazgos del draft v1
La mayoría del contenido (~80%) viene literal de las respuestas del form. Las **war stories están perfectas** — texto que el usuario redactó. Los problemas están en datos cuantitativos y personales que Claude Design alucinó:

### ⚠️ Alucinaciones a corregir antes de seguir
| Dónde | Dice | Real |
|---|---|---|
| Speaker note 10, slide 1 | "Senior SRE en Wizeline" | Usuario no especificó rol/empresa |
| Speaker notes 24, 33 | "$4.50/mo en spot", "$35/mo on-demand" | $3.65/mo stopped, ~$0.36/hr running. TensorDock no tiene "spot" |
| Speaker note 33 | "script tarda 10 minutos" | Real ~3-5min |
| Speaker note 32 | "latencia típica 800ms" | Real medido **5-9 segundos** |
| Slide ~17 | `sh NVIDIA-Linux-x86_64-570.144.run --silent --no-questions` | Bootstrap real NO instala driver (TensorDock lo trae preinstalado). Solo instala nvidia-container-toolkit + K3s |
| Slide ~19 | `helm install kserve oci://ghcr.io/kserve/charts/kserve` | URL inventada. Real: GitHub Releases tarball (ver `scripts/install-cluster-deps.sh`) |
| Speaker note 30 | "17 líneas de YAML" para InferenceService | Real ~11 líneas |
| Speaker note 29 | "modelo tarda un minuto en cargar" | Real 3-5 minutos |
| Title bar | "CNCG Cali" | Ciudad no especificada por el usuario |
| Speaker note 44 | "LinkedIn jeffry-hernandez" | Handle inventado |
| Speaker note 11 | "hace tres meses" | Cronología inventada |

## Próximos pasos (en orden)
1. **Decidir datos personales:** rol, empresa, ciudad del evento, LinkedIn
2. **Corregir alucinaciones del v1** en speaker notes (puede ser un patch directo en Claude Design o re-generar bloques específicos)
3. **Generar bloques 2-6** con prompts del `outline.md` (ya están listos para copy-paste)
4. **Iterar visual** una vez que Claude Design termine los 36 slides
5. **Reemplazar placeholders de imagen** con los archivos de `visuals/`
6. **Práctica de tiempo** — 60 min con 36 slides = ~1.7 min/slide. Cronometrar dry-run.

## Archivos clave
- `outline.md` — outline + prompts para Claude Design
- `slides-v1.html` — primer draft de Claude Design (con alucinaciones)
- `visuals/` — todos los screenshots y diagramas
- `CNCG_2023_Presentation_Template_OLD.pptx` — template CNCG (heads-up: dice "OLD", verificar si hay versión 2024+ en Slack del CNCG)

## Lección general que vale recordar
Cuando un LLM rellena gaps en un draft, lo cualitativo (war stories que el usuario redactó) sale bien. Lo cuantitativo (latencias, costos, tiempos, líneas de YAML) y lo personal (rol, empresa) se inventa con confianza. **Patrón:** todo número específico en draft AI-generado revisar contra fuente antes de leerlo en público.
