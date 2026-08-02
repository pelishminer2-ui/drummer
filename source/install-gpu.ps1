$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $here
try {
    if (-not (Test-Path ".venv")) {
        Write-Host "Creating virtual environment..."
        python -m venv .venv
    }
    $py = Join-Path $here ".venv\Scripts\python.exe"
    $pip = Join-Path $here ".venv\Scripts\pip.exe"

    Write-Host "Installing base requirements..."
    & $pip install -r requirements.txt -q

    Write-Host "Installing PyTorch with CUDA 13.2 (RTX 50-series / sm_120)..."
    & $pip uninstall torch torchaudio -y 2>$null
    & $pip install torch==2.13.0 --index-url https://download.pytorch.org/whl/cu132

    & $py -c "from gpu_backend import get_gpu_info; g=get_gpu_info(); print('Backend:', g.label)"
    Write-Host "Done. Run the app with: .venv\Scripts\python drummer_app.py"
}
finally {
    Pop-Location
}
