Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "../.."))
$ConfigPath = Join-Path $ProjectRoot "config/fog_config.yaml"
$ConfigExamplePath = Join-Path $ProjectRoot "config/fog_config.yaml.example"
$FogTool = Join-Path $ProjectRoot "tools/fog.py"
$HaibaoScript = Join-Path $ProjectRoot ".workbuddy/skills/lx-haibao/scripts/run_poster_batch.py"
$HaibaoRequirements = Join-Path $ProjectRoot ".workbuddy/skills/lx-haibao/assets/runtime/requirements.txt"

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
Write-Host "FOG 首次初始化"
Write-Host "========================================"
Write-Info "项目目录: $ProjectRoot"

if (-not (Test-Path $ConfigExamplePath)) {
    Write-Fail "统一配置模板不存在: $ConfigExamplePath"
    exit 1
}

if (-not (Test-Path $FogTool)) {
    Write-Fail "FOG 初始化工具不存在: $FogTool"
    exit 1
}

$python = Get-FogPython
if (-not $python) {
    Write-Fail "未找到 Python。请安装 Python 3，或设置环境变量 FOG_PYTHON 指向 Python 可执行文件。"
    exit 1
}
$pythonCommand = $python["Command"]
$pythonArgs = $python["Args"] -join " "
Write-Info "Python: $pythonCommand $pythonArgs"
if (-not (Test-FogPythonVersion -Python $python)) {
    Write-Fail "Python 版本过低。lx-haibao 的二维码依赖 zxing-cpp 要求 Python >= 3.10。请安装新版 Python，或设置 FOG_PYTHON 指向新版 Python。"
    exit 1
}
Write-Ok "Python 版本满足 lx-haibao 要求（>= 3.10）"

if (-not (Test-Path $ConfigPath)) {
    Copy-Item $ConfigExamplePath $ConfigPath
    Write-Ok "已创建真实配置: config/fog_config.yaml"
    Write-Warn "请先编辑 config/fog_config.yaml，填写 dataReporting、飞书普通表格、图片 API 等个人配置。"
    Write-Warn "填写完成后再次运行 .\tools\windows\install.ps1。"
    exit 1
}

if (Test-Path $HaibaoRequirements) {
    Write-Info "安装 lx-haibao Python 依赖..."
    Invoke-FogPython -Python $python -Args @("-m", "pip", "install", "-r", $HaibaoRequirements)
    if ($script:LastFogPythonExitCode -ne 0) {
        Write-Fail "lx-haibao 依赖安装失败。"
        exit 1
    }
}

if (Test-Path $HaibaoScript) {
    Write-Info "检查 lx-haibao 海报 Skill..."
    Invoke-FogPython -Python $python -Args @($HaibaoScript, "--check")
    if ($script:LastFogPythonExitCode -ne 0) {
        Write-Fail "lx-haibao 检查未通过。"
        exit 1
    }
}

Write-Info "创建 workspace 目录..."
Invoke-FogPython -Python $python -Args @($FogTool, "init")
if ($script:LastFogPythonExitCode -ne 0) {
    Write-Fail "workspace 初始化失败。"
    exit 1
}

Write-Info "检查统一配置..."
Invoke-FogPython -Python $python -Args @($FogTool, "check")
if ($script:LastFogPythonExitCode -ne 0) {
    Write-Warn "配置尚未完整。所有 Skill 都会直接读取 config/fog_config.yaml。"
    Write-Warn "请编辑 config/fog_config.yaml 后再次运行 .\tools\windows\install.ps1。"
    exit 1
}

Write-Host ""
Write-Ok "初始化完成。"
Write-Info "后续可运行 .\tools\windows\check.ps1 检查环境。"
exit 0
