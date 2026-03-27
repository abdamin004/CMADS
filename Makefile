.PHONY: install test lint run-patient run-batch dashboard setup-qdrant

# ── Setup ────────────────────────────────────────────────
install:
	pip install -r requirements.txt

# ── Testing ──────────────────────────────────────────────
test:
	python -m pytest tests/ -v

test-data:
	python -m pytest tests/test_data_pipeline.py -v

test-mas:
	python -m pytest tests/test_mas_pipeline.py -v

# ── Code Quality ─────────────────────────────────────────
lint:
	ruff check src/ pipeline/ portal/ tests/

format:
	ruff format src/ pipeline/ portal/ tests/

# ── Data Pipeline ────────────────────────────────────────
pipeline-bronze:
	python -m pipeline.bronze

pipeline-silver:
	python -m pipeline.silver

pipeline-gold:
	python -m pipeline.gold

# ── MAS Pipeline ─────────────────────────────────────────
run-patient:
	@echo "Usage: make run-patient UUID=<patient-uuid>"
	python -c "from src.orchestrator.graph import run_single_patient; run_single_patient('$(UUID)')"

run-batch:
	@echo "Usage: make run-batch BATCH=data/gold/batches/batch_1.json [MAX=5]"
	python -c "from src.orchestrator.graph import run_cohort; run_cohort('$(BATCH)', max_patients=$(or $(MAX),None))"

# ── Evaluation ───────────────────────────────────────────
evaluate:
	python -m src.evaluation.llm_judge

# ── Dashboard ────────────────────────────────────────────
dashboard:
	streamlit run portal/dashboard.py --server.port 8503

# ── Vector DB (NICE Guidelines) ─────────────────────────
setup-qdrant:
	python -m src.vectordb.setup_qdrant
