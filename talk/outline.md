# Desplegando AI-Native Apps en Kubernetes — Outline (60 min)

**Descripción del evento:**
Las apps de esta década serán AI-Native, tienen un componente de inferencia en su core. Aprende cómo utilizar Kubernetes para servir modelos de AI con un ejercicio demo de OCR utilizando KServe.

---

## 1. Timing

| Bloque | Min | Acumulado |
|---|---|---|
| Apertura | 4 | 4 |
| Fundamentos (inference / serving / quantization) | 9 | 13 |
| Por qué K8s + KServe | 11 | 24 |
| El lab (arquitectura, decisiones, tradeoffs) | 26 | 50 |
| Live demo | 5 | 55 |
| Cierre + Q&A | 5 | 60 |

Regla mental: **el lab es el corazón.** La gente se lleva las cicatrices, no las definiciones — los fundamentos los pasas rápido para llegar al "aquí está lo que rompió y cómo lo arreglé".

---

## 2. Outline slide-por-slide

### Bloque 1 — Apertura (4 min, 3 slides)

**S1. Título**
- "Desplegando AI-Native Apps en Kubernetes"
- Tu nombre, rol, fecha
- Visual: logo del evento + visual abstracto (red neuronal o pod con cerebro)

**S2. El hook**
- Frase grande: *"Las apps de esta década serán AI-Native"*
- Sub: "el componente de inferencia ya no es un add-on, es el core"
- Visual: comparación 2010s ("DB + API + UI") vs 2025s ("DB + API + **modelo** + UI")

**S3. Qué vas a ver hoy**
- 3 bullets: fundamentos rápidos, KServe, lab real con cicatrices
- Promesa: *"al final vas a saber cómo levantar un VLM real en K8s, no un Hello World"*

---

### Bloque 2 — Fundamentos rápidos (9 min, 5 slides)

**S4. Training vs Inference**
- Visual: dos cajas. Training = "una vez, pesado, batch, GPUs caras". Inference = "muchas veces, sensible a latencia, GPUs según presupuesto"
- Punto clave: **lo que vas a operar el 99% del tiempo es inference**

**S5. Qué es "model serving"**
- No es `flask app + model.predict()`
- Necesitas: batching, GPU mgmt, queueing, observability, rollouts, versioning, multi-tenancy
- Visual: app monolítica (mal) vs servidor de inference dedicado (bien)

**S6. Quantization en una slide**
- FP32 → FP16 → INT8 → INT4
- Tabla: tamaño / velocidad / pérdida de calidad
- Ejemplo concreto: "Qwen3-VL-4B en FP32 = ~16GB, en FP16 = ~8GB, cabe en una RTX 4090 con headroom"
- Mensaje: *"quantization no es opcional cuando tu GPU no es H100"*

**S7. Inference engines — el zoo**
- Tabla 2x2:
  - vLLM (LLMs/VLMs grandes, throughput)
  - TGI (HuggingFace, similar)
  - Triton (multi-framework, multi-modelo)
  - llama.cpp / Ollama (local, CPU-friendly)
- Tu pick: **vLLM** — por qué (PagedAttention, throughput, soporte de VLMs, OpenAI-compatible)

**S8. Pero... ¿y producción?**
- Frame: "ok, ya tengo vLLM corriendo en mi laptop. Ahora ¿cómo lo llevo a prod?"
- Pregunta abierta que abre el siguiente bloque

---

### Bloque 3 — Por qué K8s + KServe (11 min, 6 slides)

**S9. ¿Por qué Kubernetes para AI?**
- 4 razones: GPU scheduling, autoscaling, multi-tenancy, ecosystem (observability, ingress, secrets)
- Anti-frase: *"no es porque K8s sea genial, es porque ya está en tu org"*

**S10. Las opciones para servir en K8s**
- DIY: Deployment + Service + custom container — funciona pero tú haces todo
- Frameworks: KServe, Seldon Core, BentoML, Ray Serve
- Tu pick: **KServe** — open, CNCF, integración con Istio/Knative opcional

**S11. KServe — el modelo mental**
- Visual de bloques:
  - `InferenceService` (CR de alto nivel — "quiero servir este modelo")
  - `ServingRuntime` (cómo lo sirvo — el container + args)
  - `Predictor` (la pieza que hace predicciones)
  - `Transformer` (opcional — pre/post procesado)
  - `Explainer` (opcional — explicabilidad)
- *"Tú declaras el qué, KServe arma el cómo"*

**S12. Built-in runtimes vs custom**
- KServe trae runtimes para sklearn, xgboost, pytorch, tensorflow, **huggingface**
- El de HuggingFace usa una versión de vLLM... que probablemente no soporta tu modelo si es nuevo
- Solución: **custom ServingRuntime** apuntando a `vllm/vllm-openai`
- (Esta slide te abre la puerta para hablar del lab)

**S13. RawDeployment vs Serverless (Knative)**
- Serverless: scale-to-zero, cold starts (~30s+ con modelos grandes), requiere Knative
- RawDeployment: Deployment normal, más simple, sin scale-to-zero
- Tu pick para el lab: **RawDeployment** — *"no quiero pelearme con Knative en una sola GPU"*

**S14. Lo que K8s no te resuelve mágicamente**
- GPU drivers, container runtime config, device plugin, image pull secrets, scheduling con 1 GPU
- Frame para el lab: *"todo esto te lo vas a encontrar en producción"*

---

### Bloque 4 — El lab (26 min, ~14 slides) **[el corazón]**

**S15. Lo que construimos**
- 1 frase: *"OCR de pasaportes con un VLM open-source servido en K8s"*
- Visual: foto de pasaporte → JSON estructurado
- Tres componentes: frontend simple, API FastAPI, modelo Qwen3-VL en KServe

**S16. Arquitectura**
- Diagrama de 3 cajas con flechas:
  - Browser → Ingress (Traefik) → Frontend (nginx)
  - Frontend → /api/* → API (FastAPI)
  - API → /v1/chat/completions → InferenceService → vLLM pod (Qwen3-VL)
- 📸 *Visual sugerido: Mermaid o Excalidraw*

**S17. Por qué Qwen3-VL-4B**
- Open-source, multimodal nativo, license Apache-2.0
- Tamaño: cabe en 24GB con margen (FP16 ~8GB peak)
- Calidad: lee MRZ + extrae JSON estructurado out-of-the-box
- Anti: GPT-4V/Gemini son mejores pero no se autohospedan

**S18. Dónde correrlo — la odisea de la GPU**
- Tabla con cada cloud y qué pasó:
  - GCP: "not eligible for GPU SKUs"
  - Vultr VKE: account-gated
  - Vultr standalone: A40 partition gated
  - Lambda Labs: no aceptó la tarjeta
  - Azure: quota tickets en revisión
  - **TensorDock: 4090 a $0.36/hr running, $3.65/mo stopped** ✓
- Lección: *"el quota de GPU es un gatekeeper real, no un detalle"*

**S19. vLLM v0.11.0 — el pin que duele**
- Driver del host: 570.144 → CUDA 12.8
- vLLM `:latest` ships CUDA 13 → "forward compatibility was attempted on non supported HW"
- vLLM v0.10.2: muy viejo, no conoce `qwen3_vl`
- **v0.11.0: la única ventana que funciona** — última build con CUDA 12.x Y soporte de Qwen3-VL
- Visual: línea de tiempo de versiones de vLLM, con la "ventana" resaltada
- 📸 *Screenshot del log de error CUDA 804*

**S20. Helm chart del modelo — el código**
- `charts/model/templates/servingruntime.yaml` lado a lado con `values.yaml`
- Resaltar: `image: vllm/vllm-openai:v0.11.0` con el comentario *"⚠ DO NOT bump past v0.11.x"*
- 📸 *Screenshot real del IDE con los dos archivos abiertos*

**S21. InferenceService — el binding mínimo**
- Mostrar el yaml entero (es chico)
- Anotar: `runtimeClassName: nvidia` activa el container runtime de NVIDIA
- Anotar: NO hay `storageUri` (próxima slide explica por qué)

**S22. Tradeoff #1 — hf:// no es válido en KServe v0.14**
- Frame: "intenté `storageUri: hf://Qwen/Qwen3-VL-4B-Instruct`"
- Error literal en pantalla: *"StorageURI not supported... must be one of [gs://, s3://, pvc://, file://, https://, http://, hdfs://, webhdfs://, oci://]"*
- Solución: dropear `storageUri`, hardcodear el HF id en `--model=...`. vLLM descarga directo de HF Hub
- Lección: *"los validators del cluster no leen los release notes"*

**S23. Tradeoff #2 — Single-GPU rollout deadlock**
- 1 GPU + RollingUpdate strategy → el pod nuevo no puede surgir, el viejo no se muere → deadlock
- Solución: patchear el Deployment a `Recreate`
- Lo automatizamos en `provision.sh`
- 📸 *Screenshot de `kubectl describe pod` con "Insufficient nvidia.com/gpu"*

**S24. Tradeoff #3 — Kernel pin (la sorpresa)**
- Día 1: todo OK
- Día 2: VM se reinicia, GPU desaparece, device-plugin CrashLoopBackOff
- Causa: `unattended-upgrades` actualizó el kernel; la imagen de TensorDock instala el driver vía `.run` (no DKMS) → no se rebuilds
- Solución: bootear al kernel viejo + `apt-mark hold linux-image-*`
- Lección: *"si tu driver está fuera de DKMS, pin todo lo que se mueva"*

**S25. Tradeoff #4 — KServe install scar**
- El chart de KServe v0.14 instala recursos de ModelMesh por defecto
- Webhook apunta a un servicio que no existe → cainjector no puede inyectar caBundle → install hangs
- Solución (la documentamos en `install-cluster-deps.sh`): instalar, borrar el webhook huérfano, `helm upgrade --reuse-values`
- Lección: *"a veces el helm chart oficial trae bombas, hay que desactivarlas en el script"*

**S26. La capa de API — FastAPI con dual backend**
- Slot del código: `apps/api/app/ocr.py` con el switch `OCR_BACKEND=ollama|openai`
- Por qué dos backends: Ollama para local dev, OpenAI-compatible para producción (vLLM expone OpenAI API)
- 📸 *Screenshot del switch en código*

**S27. MRZ — trust but verify**
- El VLM lee la imagen pero puede alucinar. La MRZ (Machine Readable Zone) tiene check digits.
- Si la MRZ valida → sus campos overridean al VLM (passport_number, dob, expiry)
- Si no valida → fallback al VLM
- Visual: imagen de pasaporte con la zona MRZ resaltada, flecha → JSON con campos verificados marcados ✓
- Lección: *"siempre que puedas validar deterministicamente, hazlo. El modelo es el último recurso, no el primero"*

**S28. Frontend mínimo — sin distraerse**
- Vanilla HTML + JS + nginx que reverse-proxea `/api/*`
- A propósito sin React/Next/Vite
- Mensaje: *"el lab es del backend; el frontend es el más simple posible para no robar foco"*

**S29. Provisioning end-to-end**
- `terraform/tensordock/bootstrap.sh` (en la VM): K3s + nvidia-container-toolkit + kernel pin
- `scripts/install-cluster-deps.sh` (local): device plugin + cert-manager + KServe
- `scripts/provision.sh` (local, top-level): orquesta todo + `helm install` de los 3 charts
- 📸 *Screenshot del árbol del repo con `tree -L 3`*

**S30. El costo real**
- TensorDock 4090: $0.36/hr running, **$0.005/hr stopped ($3.65/mes)**
- Stop entre sesiones, K3s persiste en disco, viene de vuelta en 30s
- Comparación: AWS A10G ~$1/hr, GCP T4 ~$0.50/hr (cuando te dejan)

---

### Bloque 5 — Live Demo (5 min, 2 slides + acción)

**S31. Demo — qué vas a ver**
- 3 bullets con check de tiempos:
  1. Frontend → upload passport (45s)
  2. Inspeccionar el cluster en vivo (90s)
  3. Ver el log de vLLM atendiendo el request (60s)
- Plan B: si la red falla, **screenshot pre-grabado del response**

**[ACCIÓN — sin slide, terminal + browser visibles]**

```bash
# 1. Mostrar que el cluster está vivo
kubectl get inferenceservice,pods -n default

# 2. Abrir el frontend (browser ya en tab)
#    http://<vm-ip>/
#    Subir passport1.png → mostrar JSON response

# 3. Mientras procesa, en otra ventana:
kubectl logs -n default deployment/qwen3-vl-4b-predictor --tail=20
#    Apuntar al log "POST /v1/chat/completions" en tiempo real

# 4. (Si sobra tiempo) un caso edge:
#    Subir una imagen rotada o una con MRZ corrupta
#    Mostrar el fallback al VLM
```

**S32. Recap de lo que viste**
- 3 bullets: el modelo respondió, KServe orquestó, MRZ validó
- Sin texto largo — esta slide es solo un cierre visual

---

### Bloque 6 — Cierre (5 min, 4 slides)

**S33. Lessons learned**
- 5 takeaways en bullets cortos:
  1. *Ningún cloud es fácil para GPU — espera bloqueos*
  2. *Pin tus versiones de vLLM contra el driver del host*
  3. *KServe es declarativo pero los validators son estrictos*
  4. *MRZ-style validación: usa lo determinístico cuando puedas*
  5. *Helm charts + scripts de provisioning > documentación en wiki*

**S34. El repo es público**
- URL grande del repo
- "Todo lo que viste hoy: charts, scripts, código, fixtures"
- QR code → repo

**S35. Q&A**
- Pregunta semilla por si nadie pregunta primero: *"¿Cuál creen que es la pieza más frágil de todo este stack?"*

**S36. Gracias + contacto**
- Tu handle, email, etc.

---

## 3. Prompts para Claude Design

Estrategia: **subir primero el template CNCG** (`talk/CNCG_2023_Presentation_Template_OLD.pptx`) a Claude Design para que use los slide masters y la marca CNCF + **un prompt de tema** que refuerce las reglas de estilo + **un prompt por bloque** (Claude Design genera mejor cuando le das ~5-8 slides juntas con contexto).

### Setup inicial en Claude Design

1. Subir `talk/CNCG_2023_Presentation_Template_OLD.pptx` como template base
2. Pegar el prompt de tema (abajo) para reforzar reglas
3. Ir bloque por bloque pegando los prompts y aceptando/iterando

### Prompt de tema (pegar primero)

```
Estoy creando una presentación técnica de 60 minutos titulada "Desplegando AI-Native Apps en Kubernetes" para una Cloud Native Community Group (CNCG/CNCF). Audiencia: ingenieros de software/DevOps que conocen Kubernetes pero no necesariamente AI/ML.

Estilo visual — alineado con la marca CNCF/CNCG:
- Paleta de colores estricta de CNCF:
  · Primario: CNCF Blue #0086FF para títulos, énfasis y línks
  · Texto principal: CNCF Black #000000 sobre fondo blanco/claro
  · Verde #50B432 para "✓ funciona" / éxitos
  · Naranja #ED561B para "✗ falla" / tradeoffs / warnings
  · Azul secundario #058DC7 para datos de soporte
- Fuente: Arial (única tipografía permitida por la marca CNCF)
- Cuerpo de texto: 9–12pt, line-spacing 1.5
- Fondo blanco/claro, NO dark mode
- Mucho whitespace, máximo 5 bullets por slide, sin párrafos largos
- Code snippets con syntax highlighting sobre fondo claro (tema GitHub Light o similar), Arial mono no aplica — usar monospace estándar (Consolas/Menlo)
- Diagramas limpios tipo whiteboard, líneas finas, sin corporate-stock
- Iconos lineales simples; respetar los assets/branding del template CNCG donde aplique

Tono:
- Técnico pero conversacional, primera persona ("descubrí", "rompí", "arreglé")
- Honesto sobre tradeoffs y errores — no es un sales deck
- Frases punchy, sin jerga corporativa

Layout:
- Usar los slide layouts del template subido (CNCG 2023). Hay 26 layouts disponibles incluyendo "page divider", "whole page graphic", "title", "two-column body".
- Para los slides de transición entre bloques (S8, S13), usar el layout "page divider" del template.
- Para slides con un solo visual grande (S15, S35), usar "whole page graphic".
```

### Prompt — Bloque 1 (Apertura, 3 slides)

```
Genera 3 slides de apertura para la charla:

S1 - TÍTULO: "Desplegando AI-Native Apps en Kubernetes" como título grande, mi nombre y rol como subtítulo, fecha del evento. Visual abstracto evocando "modelo de AI corriendo en infraestructura" — algo como nodos de K8s con un grafo neuronal superpuesto.

S2 - HOOK: Frase central grande "Las apps de esta década serán AI-Native". Subtítulo: "el componente de inferencia ya no es un add-on, es el core". Visual de comparación: a la izquierda stack 2010s (DB + API + UI), a la derecha stack 2025s (DB + API + MODELO + UI) con MODELO en color destacado.

S3 - AGENDA: "Lo que vas a ver hoy" como título. 3 bullets: (1) Fundamentos: inference, serving, quantization (rápido), (2) KServe en K8s, (3) Lab real con cicatrices reales. Frase de cierre: "al final vas a saber cómo levantar un VLM en K8s, no un Hello World".
```

### Prompt — Bloque 2 (Fundamentos, 5 slides)

```
Genera 5 slides de fundamentos rápidos:

S4 - TRAINING VS INFERENCE: Dos columnas comparando. Training: "una vez, pesado, batch, GPUs caras". Inference: "muchas veces, latencia-sensible, GPUs según presupuesto". Mensaje grande abajo: "lo que operas el 99% del tiempo es inference".

S5 - QUÉ ES MODEL SERVING: Título "No es flask + model.predict()". 5 bullets de lo que sí necesitas: batching, GPU mgmt, queueing, observability, rollouts, versioning. Visual: a la izquierda app monolítica con un ícono de modelo embedido (mal), a la derecha app + servidor de inference dedicado (bien).

S6 - QUANTIZATION EN UNA SLIDE: Título "Quantization: por qué tu GPU consumer importa". Tabla comparando FP32, FP16, INT8, INT4 con columnas: tamaño relativo, velocidad relativa, pérdida de calidad. Caja resaltada abajo: "Qwen3-VL-4B en FP32 = 16GB, en FP16 = 8GB → cabe en RTX 4090 24GB con margen".

S7 - INFERENCE ENGINES — EL ZOO: Grid 2x2 con 4 engines. vLLM (LLMs grandes, throughput, OpenAI-compatible). TGI (HuggingFace native). Triton (multi-framework). llama.cpp/Ollama (local, CPU-friendly). Una caja destacada al final: "Mi pick: vLLM. Por qué: PagedAttention, soporte de VLMs, API estándar".

S8 - PUENTE: Pregunta grande en pantalla "OK, vLLM corre en mi laptop. ¿Cómo lo llevo a producción?". Sin más texto. Esto cierra el bloque y abre el siguiente.
```

### Prompt — Bloque 3 (KServe, 6 slides)

```
Genera 6 slides sobre Kubernetes y KServe:

S9 - ¿POR QUÉ K8S PARA AI?: Título. 4 razones en cards: (1) GPU scheduling, (2) Autoscaling, (3) Multi-tenancy, (4) Ecosystem (observability/ingress/secrets). Cita pequeña al pie: "no es porque K8s sea genial, es porque ya está en tu org".

S10 - OPCIONES PARA SERVIR: Comparación. DIY (Deployment + Service + custom container) vs Frameworks (KServe, Seldon Core, BentoML, Ray Serve). Mi pick: KServe — open, CNCF, integración Istio/Knative opcional.

S11 - KSERVE — MODELO MENTAL: Diagrama de bloques con relaciones. Caja central "InferenceService" (CR de alto nivel). Conectado a "ServingRuntime" (cómo lo sirvo) y a "Predictor" (la pieza que predice). Cajas opcionales en gris: "Transformer" (pre/post-procesado) y "Explainer" (explicabilidad). Frase abajo: "Tú declaras el qué, KServe arma el cómo".

S12 - BUILT-IN VS CUSTOM RUNTIMES: KServe trae runtimes para sklearn, xgboost, pytorch, tensorflow, huggingface. Pero el de HuggingFace empaqueta una versión vieja de vLLM. Si tu modelo es nuevo, vas a necesitar un ServingRuntime custom apuntando a vllm/vllm-openai.

S13 - RAWDEPLOYMENT VS SERVERLESS: Dos columnas. Serverless (Knative): scale-to-zero, cold starts ~30s+ con modelos grandes, requiere Knative. RawDeployment: Deployment normal, simple, sin scale-to-zero. Mi pick: RawDeployment — frase "no quiero pelearme con Knative con una sola GPU".

S14 - LO QUE K8S NO TE RESUELVE: Lista de cosas que igual te toca: GPU drivers, container runtime config, device plugin, image pull secrets, scheduling con 1 GPU. Frase de cierre: "todo esto te lo vas a encontrar en producción".
```

### Prompt — Bloque 4 (Lab, ~14 slides) **— el más importante**

```
Genera ~14 slides técnicas sobre la implementación del lab. Estilo: muy visual, con code snippets reales, diagramas, y screenshots cuando indique. Cada tradeoff merece su propia slide con error real visible.

S15 - LO QUE CONSTRUIMOS: Frase central "OCR de pasaportes con un VLM open-source servido en K8s". Visual flow: imagen de pasaporte → flecha → JSON estructurado con campos (surname, passport_number, dob, etc.).

S16 - ARQUITECTURA: Diagrama de 3 cajas con flechas en orden: Browser → Ingress (Traefik) → Frontend (nginx) → API (FastAPI) → InferenceService → vLLM pod (Qwen3-VL). [Yo voy a insertar mi diagrama Excalidraw después.]

S17 - POR QUÉ QWEN3-VL-4B: 4 bullets: open-source Apache 2.0, multimodal nativo, fits en 24GB FP16, calidad suficiente para MRZ y JSON. Anti-bullet: "GPT-4V/Gemini son mejores pero no self-hosted".

S18 - LA ODISEA DE LA GPU: Título "Encontrar una GPU es la mitad del trabajo". Tabla con 6 filas: GCP (not eligible), Vultr VKE (gated), Vultr standalone A40 (gated), Lambda Labs (no aceptó tarjeta), Azure (tickets en revisión), TensorDock (✓ funciona). Última fila destacada en verde con "$0.36/hr running, $3.65/mo stopped".

S19 - VLLM v0.11.0 — EL PIN QUE DUELE: Visual de línea de tiempo horizontal de versiones de vLLM (v0.10.2 → v0.11.0 → v0.11.2 → v0.12.0 → latest). Marcar v0.11.0 con ✓ verde. Marcar las demás con ✗ rojo y razón corta: v0.10.2 "no conoce qwen3_vl", v0.11.2+ "CUDA 13 toolkit, no compatible con driver 570". [Voy a insertar screenshot del log de error CUDA 804.]

S20 - HELM CHART DEL MODELO: Mostrar code snippets lado a lado. Izquierda: charts/model/values.yaml (model.id, runtime.image, resources). Derecha: charts/model/templates/servingruntime.yaml renderizando los valores. Callout naranja flotante apuntando a la línea `image: vllm/vllm-openai:v0.11.0` con el texto "⚠ pinned a v0.11.0 — más nuevo = CUDA 13 incompatible con driver 570; más viejo = no soporta qwen3_vl".

S21 - INFERENCESERVICE — EL BINDING MÍNIMO: Code snippet completo del InferenceService (es chico, ~10 líneas). Anotaciones a la derecha apuntando a: runtimeClassName: nvidia, model.runtime: vllm-qwen-vl. Caja de aviso: "NO hay storageUri (siguiente slide explica por qué)".

S22 - TRADEOFF #1: hf:// NO ES VÁLIDO EN v0.14: Título "El validator de KServe v0.14 no acepta hf://". Block de error literal: "StorageURI not supported: must be one of [gs://, s3://, pvc://, file://, https://, ...]". Solución: dropear storageUri, hardcodear el HF id en --model=Qwen/Qwen3-VL-4B-Instruct. vLLM descarga directo de HF Hub al startup.

S23 - TRADEOFF #2: SINGLE-GPU ROLLOUT DEADLOCK: 1 GPU + RollingUpdate → pod nuevo no puede surgir, viejo no muere → deadlock. Visual: dos pods, uno corriendo (verde), uno Pending (amarillo) con texto "Insufficient nvidia.com/gpu". Solución: patchear Deployment a Recreate strategy. Snippet del kubectl patch.

S24 - TRADEOFF #3: KERNEL PIN: Título "Cuando el host se actualiza solo y se rompe el driver". Timeline: día 1 todo OK → noche día 2 unattended-upgrades sube kernel → día 3 GPU desaparece. Causa: TensorDock instala driver vía .run installer (no DKMS) → no se rebuilds en kernel nuevo. Solución: apt-mark hold linux-image-* + grub default fijo al kernel viejo. Lección destacada: "si tu driver está fuera de DKMS, pin todo lo que se mueva".

S25 - TRADEOFF #4: KSERVE INSTALL SCAR: El chart de KServe v0.14 instala recursos de ModelMesh que apuntan a un servicio inexistente → cainjector no puede inyectar caBundle → install hangs. Solución (automatizada en install-cluster-deps.sh): kubectl delete validatingwebhookconfiguration modelmesh-... && helm upgrade --reuse-values. Lección: "a veces el chart oficial trae bombas, hay que desactivarlas en el script".

S26 - LA CAPA DE API — DUAL BACKEND: Code snippet de apps/api/app/ocr.py mostrando el switch OCR_BACKEND=ollama|openai. Diagrama abajo: dev local → Ollama, cluster → vLLM (vía OpenAI-compatible API). Frase: "vLLM expone /v1/chat/completions, así que el código de prod es el mismo cliente OpenAI con base_url distinto".

S27 - MRZ — TRUST BUT VERIFY: Imagen de pasaporte con la zona MRZ resaltada (las dos líneas de abajo). Flecha → JSON con campos. Resaltar en verde los campos validados por MRZ check-digits (passport_number, dob, expiry). Mensaje grande: "siempre que puedas validar deterministicamente, hazlo. El modelo es el último recurso, no el primero".

S28 - FRONTEND MÍNIMO: Vanilla HTML + JS + nginx que reverse-proxea /api/*. A propósito sin React/Next. Frase: "el lab es del backend; el frontend es lo más simple posible".

S29 - PROVISIONING END-TO-END: Diagrama de 3 capas. (1) terraform/tensordock/bootstrap.sh en la VM: K3s + nvidia-container-toolkit + kernel pin. (2) scripts/install-cluster-deps.sh local: device plugin + cert-manager + KServe. (3) scripts/provision.sh local top-level: orquesta + helm install x3. [Insertar screenshot de tree -L 3 del repo.]

S30 - EL COSTO REAL: Caja grande con números: TensorDock 4090 $0.36/hr running, $0.005/hr stopped (~$3.65/mes). Comparación: AWS A10G ~$1/hr, GCP T4 ~$0.50/hr (cuando te dejan). Mensaje: "stop entre sesiones, K3s persiste, vuelve en 30s".
```

### Prompt — Bloque 5 (Demo, 2 slides)

```
Genera 2 slides para enmarcar el live demo de 5 minutos:

S31 - QUÉ VAS A VER: Título "Demo en vivo". 3 pasos numerados grandes: (1) Frontend: upload passport → JSON, (2) Inspeccionar el cluster, (3) Ver el log de vLLM en tiempo real. Caja pequeña abajo: "Plan B: screenshot pre-grabado por si la red falla".

S32 - RECAP DEL DEMO: Después del demo. 3 bullets de cierre: (1) El modelo respondió en ~5s, (2) KServe orquestó la llamada, (3) MRZ validó el output. Slide visual y limpia, sin texto largo.
```

### Prompt — Bloque 6 (Cierre, 4 slides)

```
Genera 4 slides de cierre:

S33 - LESSONS LEARNED: 5 takeaways en bullets numerados grandes: (1) Ningún cloud es fácil para GPU — espera bloqueos, (2) Pin tus versiones de vLLM contra el driver del host, (3) KServe es declarativo pero los validators son estrictos, (4) MRZ-style: usa lo determinístico cuando puedas, (5) Helm charts + scripts > documentación en wiki.

S34 - REPO PÚBLICO: URL grande del repo en mono. "Todo lo que viste hoy: charts, scripts, código, fixtures". QR code grande a la derecha apuntando al repo.

S35 - Q&A: Solo "Q&A" gigante en pantalla. Pregunta semilla pequeña abajo por si nadie pregunta: "¿Cuál creen que es la pieza más frágil de todo este stack?".

S36 - GRACIAS: "Gracias" grande. Mi handle, email, link al repo, link a slides. Visual minimalista.
```

---

## 4. Visuals para capturar antes del talk

Cuando enciendas la VM de nuevo, capturá estos screenshots — son los que más impacto tienen en el deck:

1. **Diagrama de arquitectura** (Excalidraw o Mermaid) — para S16
2. **Log del error CUDA 804** — para S19 (reproducible cambiando el image tag a `:latest` y mirando logs)
3. **Output de `kubectl get inferenceservice,pods,svc -n default`** con todo Ready — para S29 o S31
4. **Screenshot del IDE** con `values.yaml` y `servingruntime.yaml` lado a lado — para S20
5. **Screenshot del frontend** con un pasaporte ya procesado y JSON visible — para S15 y plan B del demo
6. **`tree -L 3`** del repo — para S29
7. **Foto del `apt-mark hold` y grub default aplicados** — para S24
