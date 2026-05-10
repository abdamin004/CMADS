.PHONY: install test lint run-patient run-batch dashboard setup-qdrant \
        thesis thesis-clean thesis-watch

# ── Setup ────────────────────────────────────────────────
install:
	pip install -r requirements.txt

# ── Testing ──────────────────────────────────────────────
test:
	python3 -m pytest tests/ -v

test-data:
	python3 -m pytest tests/test_data_pipeline.py -v

test-mas:
	python3 -m pytest tests/test_mas_pipeline.py -v

# ── Code Quality ─────────────────────────────────────────
lint:
	ruff check src/ pipeline/ portal/ tests/

format:
	ruff format src/ pipeline/ portal/ tests/

# ── Data Pipeline ────────────────────────────────────────
pipeline-bronze:
	python3 -m pipeline.bronze

pipeline-silver:
	python3 -m pipeline.silver

pipeline-gold:
	python3 -m pipeline.gold

# ── MAS Pipeline ─────────────────────────────────────────
run-patient:
	@echo "Usage: make run-patient UUID=<patient-uuid>"
	python3 -c "from src.orchestrator.graph import run_single_patient; run_single_patient('$(UUID)')"

run-batch:
	@echo "Usage: make run-batch BATCH=data/gold/batches/batch_1.json [MAX=5]"
	python3 -c "from src.orchestrator.graph import run_cohort; run_cohort('$(BATCH)', max_patients=$(or $(MAX),None))"

# ── Evaluation ───────────────────────────────────────────
evaluate:
	python3 -m src.evaluation.llm_judge

# ── Dashboard ────────────────────────────────────────────
dashboard:
	streamlit run portal/dashboard.py --server.port 8503

# ── Vector DB (NICE Guidelines) ─────────────────────────
setup-qdrant:
	python3 -m src.vectordb.setup_qdrant

# ── Thesis (LaTeX) ──────────────────────────────────────
# Builds thesis/main.pdf. Prefers tectonic if available (single-pass),
# falls back to a 2-pass pdflatex + bibtex + pdflatex × 2 cycle.
TECTONIC := $(shell command -v tectonic 2>/dev/null || ([ -x /tmp/tectonic ] && echo /tmp/tectonic) || true)

thesis:
	@cd thesis && if [ -n "$(TECTONIC)" ]; then \
		echo "Building with $(TECTONIC)…"; \
		$(TECTONIC) main.tex; \
	elif command -v pdflatex >/dev/null 2>&1; then \
		echo "Building with pdflatex (3-pass)…"; \
		pdflatex -interaction=nonstopmode -halt-on-error main.tex && \
		bibtex main && \
		pdflatex -interaction=nonstopmode -halt-on-error main.tex && \
		pdflatex -interaction=nonstopmode -halt-on-error main.tex; \
	else \
		echo "Neither tectonic nor pdflatex on PATH. Install one:"; \
		echo "  curl -fsSL https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.15.0/tectonic-0.15.0-aarch64-apple-darwin.tar.gz -o /tmp/tectonic.tar.gz && tar -xzf /tmp/tectonic.tar.gz -C /tmp"; \
		exit 1; \
	fi
	@echo "Built: thesis/main.pdf ($$(mdls -name kMDItemNumberOfPages thesis/main.pdf 2>/dev/null | awk '{print $$3}') pages)"

thesis-clean:
	cd thesis && rm -f *.aux *.bbl *.blg *.idx *.ilg *.ind *.lof *.log \
	                   *.lot *.out *.synctex.gz *.toc *.fdb_latexmk *.fls \
	                   *.nav *.snm *.vrb main.pdf
	@echo "Cleaned thesis build artifacts."

# Rebuild on every save (requires fswatch — `brew install fswatch`).
thesis-watch:
	@command -v fswatch >/dev/null 2>&1 || { echo "fswatch missing — install with 'brew install fswatch'"; exit 1; }
	@echo "Watching thesis/*.tex and thesis/*.bib — Ctrl-C to stop."
	@$(MAKE) thesis
	@fswatch -o thesis/*.tex thesis/*.bib | xargs -n1 -I{} $(MAKE) thesis
