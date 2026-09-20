.PHONY: install run debug clean lint lint-strict serve

VENV_BIN = .venv/bin
PYTHON_SYS = python3

PYTHON = $(VENV_BIN)/python
FLAKE8 = $(VENV_BIN)/flake8
MYPY   = $(VENV_BIN)/mypy
UVICORN = $(VENV_BIN)/uvicorn

MAP ?= maps/easy/01_linear_path.txt

install:
	@echo "CREATING VIRTUAL ENVIRONMENT (.venv)..."
	@uv venv || $(PYTHON_SYS) -m venv .venv
	@echo "Installing dependencies..."
	@uv pip install -e . flake8 mypy || \
	$(VENV_BIN)/pip install -e . flake8 mypy
	@echo "Installation completed."

run:
	@$(PYTHON) fly_in.py -i "$(MAP)" $(ARGS) || true

serve:
	@echo "Booting API server and opening browser..."
	@$(PYTHON) fly_in.py --serve

stop:
	@echo "Shutting down background API server..."
	@pid=$$(lsof -ti:8080); \
	if [ -n "$$pid" ]; then  kill -9 $$pid; \
	else echo "Port 8080 is already clear."; fi

debug:
	$(PYTHON) -m pdb fly_in.py -i $(MAP)

clean:
	@echo "CLEANING CACHE AND VENV"
	@rm -rf __pycache__ .mypy_cache 42_fly_in.egg-info \
	.pytest_cache */__pycache__ .venv

lint:
	$(FLAKE8) .
	$(MYPY) . --warn-return-any --warn-unused-ignores \
	--ignore-missing-imports --disallow-untyped-defs --check-untyped-defs

lint-strict:
	$(FLAKE8) .
	$(MYPY) . --strict
