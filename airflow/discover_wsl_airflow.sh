#!/usr/bin/env bash
# ==============================================================================
# APIShield — WSL Apache Airflow Discovery & Verification Script
# Run this inside your WSL Ubuntu shell to discover your existing Airflow environment.
# Safe & non-destructive: does not modify or reset your database or configurations.
# ==============================================================================

echo "========================================================"
echo "      APIShield — WSL Apache Airflow Discovery"
echo "========================================================"

# 1. Python & Virtual Environment Inspection
echo ""
echo "[1] Python & Environment:"
echo "--------------------------------------------------------"
echo "Active Python executable: $(which python3 || which python || echo 'None found')"
python3 --version 2>/dev/null || python --version 2>/dev/null || echo "Python not found"

if [ -n "$VIRTUAL_ENV" ]; then
    echo "Active Virtualenv: YES -> $VIRTUAL_ENV"
else
    echo "Active Virtualenv: NO (running in system environment)"
    echo "Common venv locations to check:"
    for venv_path in ~/.virtualenvs/* ~/.local/share/virtualenvs/* ~/airflow_venv ~/venv ~/.venv; do
        if [ -d "$venv_path" ]; then
            echo "  - Found candidate venv: $venv_path"
        fi
    done
fi

# 2. Airflow Executable & Path
echo ""
echo "[2] Airflow Executable & Version:"
echo "--------------------------------------------------------"
AIRFLOW_BIN=$(which airflow 2>/dev/null)
if [ -n "$AIRFLOW_BIN" ]; then
    echo "Airflow binary on PATH: $AIRFLOW_BIN"
    AIRFLOW_VERSION=$(airflow version 2>/dev/null)
    echo "Airflow version: $AIRFLOW_VERSION"
else
    echo "Airflow NOT on current PATH."
    echo "Tip: If installed in a specific virtualenv, activate it first:"
    echo "  source /path/to/venv/bin/activate"
fi

# 3. AIRFLOW_HOME & DAGs Directory
echo ""
echo "[3] Airflow Home & DAG Directory:"
echo "--------------------------------------------------------"
EFFECTIVE_AIRFLOW_HOME="${AIRFLOW_HOME:-$HOME/airflow}"
echo "Effective AIRFLOW_HOME: $EFFECTIVE_AIRFLOW_HOME"

if [ -n "$AIRFLOW_BIN" ]; then
    DAGS_DIR=$(airflow config get-value core dags_folder 2>/dev/null || echo "$EFFECTIVE_AIRFLOW_HOME/dags")
    echo "Configured DAGs folder: $DAGS_DIR"

    # Metadata database check (without printing credentials)
    SQL_CONN=$(airflow config get-value database sql_alchemy_conn 2>/dev/null || airflow config get-value core sql_alchemy_conn 2>/dev/null)
    DB_TYPE=$(echo "$SQL_CONN" | cut -d':' -f1)
    echo "Metadata DB Type: ${DB_TYPE:-sqlite/default}"
else
    DAGS_DIR="$EFFECTIVE_AIRFLOW_HOME/dags"
    echo "Assumed DAGs folder: $DAGS_DIR"
fi

# 4. Check Running Airflow Services
echo ""
echo "[4] Running Airflow Processes in WSL:"
echo "--------------------------------------------------------"
pgrep -fl "airflow (scheduler|webserver|api-server|worker)" || echo "No active Airflow services currently running."

# 5. Accessibility from Windows Workspace
echo ""
echo "[5] Workspace Connectivity:"
echo "--------------------------------------------------------"
WIN_WS="/mnt/d/College/3rd_Year/MLOPS/CP/backend"
if [ -d "$WIN_WS" ]; then
    echo "APIShield Windows backend mounted at: $WIN_WS"
    echo "DAGs in workspace: $WIN_WS/airflow/dags"
    ls -la "$WIN_WS/airflow/dags" 2>/dev/null || true
else
    echo "Windows mount not detected at $WIN_WS"
fi

echo ""
echo "========================================================"
echo "Discovery complete. Report the output above to APIShield."
echo "========================================================"
