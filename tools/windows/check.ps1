Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "../.."))
$ConfigPath = Join-Path $ProjectRoot "config/fog_config.yaml"
$ConfigExamplePath = Join-Path $ProjectRoot "config/fog_config.yaml.example"
$FogTool = Join-Path $ProjectRoot "tools/fog.py"
$HaibaoScript = Join-Path $ProjectRoot ".workbuddy/skills/lx-haibao/scripts/run_poster_batch.py"

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message"
}

function Write-Ok {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Fail {
    param([string]$Message)
    Write-Host "[FAIL] $Message" -ForegroundColor Red
}

function Test-PathRequired {
    param(
        [string]$Path,
        [string]$Label
    )
    if (Test-Path $Path) {
        Write-Ok "${Label}: $Path"
        return $true
    }
    Write-Fail "${Label} 不存在: $Path"
    return $false
}

function Get-FogPython {
    if ($env:FOG_PYTHON) {
        return @{ Command = $env:FOG_PYTHON; Args = @() }
    }

    $py = Get-Command "py" -ErrorAction SilentlyContinue
    if ($py) {
        return @{ Command = $py.Source; Args = @("-3") }
    }

    $python = Get-Command "python" -ErrorAction SilentlyContinue
    if ($python) {
        return @{ Command = $python.Source; Args = @() }
    }

    return $null
}

function Invoke-FogPython {
    param(
        [hashtable]$Python,
        [string[]]$Args
    )
    $allArgs = @()
    $allArgs += $Python["Args"]
    $allArgs += $Args
    & $Python["Command"] @allArgs
    $script:LastFogPythonExitCode = $LASTEXITCODE
}

function Test-FogPythonVersion {
    param([hashtable]$Python)
    Invoke-FogPython -Python $Python -Args @("-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)")
    return ($script:LastFogPythonExitCode -eq 0)
}

Write-Host ""
Write-Host "FOG 环境检查"
Write-Host "========================================"
Write-Info "项目目录: $ProjectRoot"

$failed = $false

if (-not (Test-PathRequired (Join-Path $ProjectRoot ".workbuddy") ".workbuddy 目录")) { $failed = $true }
if (-not (Test-PathRequired (Join-Path $ProjectRoot ".workbuddy/skills/lx-init") "lx-init Skill")) { $failed = $true }
if (-not (Test-PathRequired (Join-Path $ProjectRoot ".workbuddy/skills/lx_shujuku") "lx_shujuku Skill")) { $failed = $true }
if (-not (Test-PathRequired (Join-Path $ProjectRoot ".workbuddy/skills/lx-feishudocs") "lx-feishudocs Skill")) { $failed = $true }
if (-not (Test-PathRequired (Join-Path $ProjectRoot ".workbuddy/skills/lx-zhutichaibiao") "lx-zhutichaibiao Skill")) { $failed = $true }
if (-not (Test-PathRequired (Join-Path $ProjectRoot ".workbuddy/skills/lx-haibao") "lx-haibao Skill")) { $failed = $true }
if (-not (Test-PathRequired $ConfigExamplePath "统一配置模板")) { $failed = $true }
if (-not (Test-PathRequired $FogTool "FOG 初始化工具")) { $failed = $true }
if (-not (Test-PathRequired $HaibaoScript "lx-haibao 检查脚本")) { $failed = $true }

$python = Get-FogPython
$pythonVersionOk = $false
if (-not $python) {
    Write-Fail "未找到 Python。请安装 Python 3，或设置环境变量 FOG_PYTHON 指向 Python 可执行文件。"
    $failed = $true
} else {
    $pythonCommand = $python["Command"]
    $pythonArgs = $python["Args"] -join " "
    Write-Info "Python: $pythonCommand $pythonArgs"
    Invoke-FogPython -Python $python -Args @("--version")
    if ($script:LastFogPythonExitCode -ne 0) {
        Write-Fail "Python 无法运行。"
        $failed = $true
    } else {
        Write-Ok "Python 可用"
        if (Test-FogPythonVersion -Python $python) {
            Write-Ok "Python 版本满足 lx-haibao 要求（>= 3.10）"
            $pythonVersionOk = $true
        } else {
            Write-Fail "Python 版本过低。lx-haibao 的二维码依赖 zxing-cpp 要求 Python >= 3.10。请安装新版 Python，或设置 FOG_PYTHON 指向新版 Python。"
            $failed = $true
        }
    }
}

if (-not (Test-Path $ConfigPath)) {
    Write-Warn "真实配置不存在: $ConfigPath"
    Write-Warn "首次使用请运行 .\tools\windows\install.ps1 复制模板，然后编辑 config/fog_config.yaml。"
    $failed = $true
} elseif ($python) {
    Write-Info "检查统一配置..."
    Invoke-FogPython -Python $python -Args @($FogTool, "check")
    if ($script:LastFogPythonExitCode -ne 0) {
        Write-Fail "统一配置检查未通过。请编辑 config/fog_config.yaml 后重试。"
        $failed = $true
    } else {
        Write-Ok "统一配置检查通过"
    }
}

if ($pythonVersionOk -and (Test-Path $HaibaoScript)) {
    Write-Info "检查 lx-haibao 海报 Skill..."
    Invoke-FogPython -Python $python -Args @($HaibaoScript, "--check")
    if ($script:LastFogPythonExitCode -ne 0) {
        Write-Fail "lx-haibao 检查未通过。请先安装依赖：python -m pip install -r .workbuddy/skills/lx-haibao/requirements.txt"
        $failed = $true
    } else {
        Write-Ok "lx-haibao 检查通过"
    }
}

if ($failed) {
    Write-Host ""
    Write-Fail "检查未通过。"
    exit 1
}

Write-Host ""
Write-Ok "检查通过。"
exit 0
