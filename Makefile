# SmartMonitor — build one diagram + make an MP4 animation
SHELL := /bin/sh

# Source + outputs
SRC_PUML      := docs/overview/SmartMonitor_Lab_Sequence.puml
SVG           := $(SRC_PUML:.puml=.svg)
OUT_DIR       := docs/overview/build
MP4           := docs/overview/SmartMonitor_Lab_Sequence.mp4

# Animation knobs
FPS  ?= 20
SECS ?= 20

# Use Docker for tools by default (safer on Windows)
docker ?= 1

# ---- default -------------------------------------------------------
.PHONY: default
default: svg

# ---- PlantUML to SVG ----------------------------------------------
.PHONY: svg
svg: $(SVG)

$(SVG): $(SRC_PUML)
	@mkdir -p "$(dir $@)"
	@echo "→ PUML → SVG: $<"
ifeq ($(docker),1)
	@docker run --rm -v "$(CURDIR):/work" -w /work plantuml/plantuml:latest -tsvg "$<"
else
	@plantuml -tsvg "$<"
endif

# ---- Frames via Puppeteer (installs deps inside container) --------
# --- animation config ---
SVG        ?= docs/overview/SmartMonitor_Lab_Sequence.svg
OUT_DIR    ?= docs/overview/build
FPS        ?= 20
SECS       ?= 20
MP4        ?= docs/overview/SmartMonitor_Lab_Sequence.mp4

# Use Docker by default
docker ?= 1
VERBOSE ?= 0

.PHONY: anim-frames
anim-frames: $(SVG)
	@test -f "$(SVG)" || { echo "SVG not found: $(SVG)"; exit 1; }
	@mkdir -p "$(OUT_DIR)"
ifeq ($(docker),1)
	@echo " Rendering frames with Puppeteer container"
	@docker run --rm \
	  -e NODE_PATH=/home/pptruser/node_modules \
	  -e PUPPETEER_SKIP_DOWNLOAD=1 \
	  -v "$(CURDIR):/work" -w /work \
	  ghcr.io/puppeteer/puppeteer:latest \
	  bash -lc ' \
	    set -e$(if $(filter 1,$(VERBOSE)), -x,); \
	    node docs/overview/build/render.js \
	      "$(SVG)" "$(OUT_DIR)" "$(FPS)" "$(SECS)" \
	  '
else
	@node docs/overview/build/render.js "$(SVG)" "$(OUT_DIR)" "$(FPS)" "$(SECS)"
endif
	@echo "✔ Frames written to $(OUT_DIR)"

.PHONY: anim-mp4
anim-mp4: anim-frames
ifeq ($(docker),1)
	@echo " Encoding MP4 with ffmpeg container"
	@docker run --rm -v "$(CURDIR):/work" -w /work jrottenberg/ffmpeg:4.4-alpine \
	  -y -framerate $(FPS) \
	  -i "$(OUT_DIR)/frame_%05d.png" \
	  -pix_fmt yuv420p -movflags +faststart "$(MP4)"
else
	@ffmpeg -y -framerate $(FPS) \
	  -i "$(OUT_DIR)/frame_%05d.png" \
	  -pix_fmt yuv420p -movflags +faststart "$(MP4)"
endif
	@echo "✔ MP4 written to $(MP4)"