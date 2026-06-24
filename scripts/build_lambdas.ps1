# build_lambdas.ps1 — Empacota as 3 Lambdas para deploy no AWS Lambda (Amazon Linux x86_64).
# Requer: Python 3.12+, pip.
# Gera: packages/initializer.zip, packages/integrator.zip, packages/mcp_server.zip
#
# Instala dependências com wheels Linux compatíveis:
#   --platform manylinux2014_x86_64
#   --implementation cp
#   --python-version 3.12
#   --only-binary=:all:
#
# boto3/botocore são EXCLUÍDOS: Lambda runtime os fornece.
# Se alguma dependência não tiver wheel compatível, o script falha.
# ZIPs são criados com Python zipfile para garantir separadores POSIX (/).
#
# Uso: .\scripts\build_lambdas.ps1

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$PACKAGES = Join-Path $ROOT "packages"
$SRC = Join-Path $ROOT "src"

# Limpar tudo
if (Test-Path $PACKAGES) { Remove-Item -Recurse -Force $PACKAGES }
New-Item -ItemType Directory -Path $PACKAGES | Out-Null

Write-Host "=== Building Lambda packages (target: Linux x86_64, Python 3.12) ==="
Write-Host "    boto3/botocore EXCLUDED (provided by Lambda runtime)"

function Install-LambdaDeps {
    param([string]$RequirementsFile, [string]$TargetDir)

    Write-Host "  Installing dependencies (manylinux2014_x86_64, cp312, only-binary)..."
    $pipArgs = @(
        "-m", "pip", "install",
        "--platform", "manylinux2014_x86_64",
        "--implementation", "cp",
        "--python-version", "3.12",
        "--only-binary=:all:",
        "--target", $TargetDir,
        "--upgrade",
        "-r", $RequirementsFile
    )

    $result = & python @pipArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error "pip install failed. Some dependencies may not have Linux wheels.`n$result"
        exit 1
    }
}

function Remove-Unnecessary {
    param([string]$BuildDir)
    # Remove boto3, botocore, s3transfer, jmespath se vieram como transitivas
    foreach ($pattern in @("boto3", "botocore", "s3transfer", "jmespath")) {
        Get-ChildItem -Path $BuildDir -Directory -Filter $pattern -ErrorAction SilentlyContinue |
            ForEach-Object { Remove-Item -Recurse -Force $_.FullName }
        Get-ChildItem -Path $BuildDir -Directory -Filter "$pattern-*dist-info" -ErrorAction SilentlyContinue |
            ForEach-Object { Remove-Item -Recurse -Force $_.FullName }
    }
    # Remove __pycache__
    Get-ChildItem -Path $BuildDir -Directory -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item -Recurse -Force $_.FullName }
    # Remove *.pyc
    Get-ChildItem -Path $BuildDir -Recurse -Filter "*.pyc" -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item -Force $_.FullName }
}

function New-PosixZip {
    param([string]$SourceDir, [string]$ZipPath)
    # Usa Python zipfile para garantir separadores POSIX (/) nos nomes internos
    $pythonScript = @"
import zipfile, os, sys

source_dir = sys.argv[1]
zip_path = sys.argv[2]

with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(source_dir):
        for file in sorted(files):
            abs_path = os.path.join(root, file)
            # arcname relativo ao source_dir, com separadores POSIX
            rel_path = os.path.relpath(abs_path, source_dir).replace('\\\\', '/')
            zf.write(abs_path, rel_path)

print(f"Created {zip_path} with {len(zipfile.ZipFile(zip_path).namelist())} entries")
"@
    $result = echo $pythonScript | python - $SourceDir $ZipPath 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error "ZIP creation failed:`n$result"
        exit 1
    }
    Write-Host "  $result"
}

function Build-Lambda {
    param(
        [string]$Name,
        [string[]]$SourceDirs,
        [string[]]$ExtraDirs,
        [string]$RequirementsFile
    )
    Write-Host "`n--- Packaging $Name ---"
    $buildDir = Join-Path $PACKAGES "${Name}_build"
    if (Test-Path $buildDir) { Remove-Item -Recurse -Force $buildDir }
    New-Item -ItemType Directory -Path $buildDir | Out-Null

    # Instalar dependências Linux
    if ($RequirementsFile -and (Test-Path $RequirementsFile)) {
        Install-LambdaDeps -RequirementsFile $RequirementsFile -TargetDir $buildDir
        Remove-Unnecessary -BuildDir $buildDir
    }

    # Copiar código fonte (na raiz do ZIP)
    foreach ($dir in $SourceDirs) {
        $srcPath = Join-Path $SRC $dir
        $destPath = Join-Path $buildDir $dir
        Write-Host "  Copying src/$dir -> $dir/"
        Copy-Item -Recurse -Force $srcPath $destPath
        # Limpar __pycache__ do código copiado
        Get-ChildItem -Path $destPath -Directory -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue |
            ForEach-Object { Remove-Item -Recurse -Force $_.FullName }
    }

    # Copiar diretórios extras na raiz do ZIP
    foreach ($dir in $ExtraDirs) {
        $srcPath = Join-Path $ROOT $dir
        $destPath = Join-Path $buildDir $dir
        Write-Host "  Copying $dir -> $dir/"
        Copy-Item -Recurse -Force $srcPath $destPath
    }

    # Criar ZIP com separadores POSIX
    $zipPath = Join-Path $PACKAGES "$Name.zip"
    Write-Host "  Creating $Name.zip (POSIX paths)..."
    New-PosixZip -SourceDir $buildDir -ZipPath $zipPath

    # Limpar build dir
    Remove-Item -Recurse -Force $buildDir

    $size = [math]::Round((Get-Item $zipPath).Length / 1MB, 2)
    Write-Host "  Done: $Name.zip ($size MB)"
}

# --- Requirements por Lambda ---
# boto3/botocore NÃO incluídos (Lambda runtime fornece)

$reqsInitializer = Join-Path $PACKAGES "reqs-initializer.txt"
# Initializer usa pydantic (modelos) — não precisa httpx nem mcp
@"
pydantic>=2.0.0
"@ | Set-Content $reqsInitializer

$reqsIntegrator = Join-Path $PACKAGES "reqs-integrator.txt"
# Integrator usa pydantic (modelos) + httpx (MCP client HTTP)
@"
pydantic>=2.0.0
httpx>=0.27.0
"@ | Set-Content $reqsIntegrator

$reqsMcpServer = Join-Path $PACKAGES "reqs-mcp-server.txt"
# MCP Server usa mcp (FastMCP) + mangum (ASGI→Lambda) + uvicorn (ASGI server)
@"
mcp>=1.0.0
mangum>=0.17.0
pydantic>=2.0.0
uvicorn>=0.30.0
"@ | Set-Content $reqsMcpServer

# --- Initializer ---
# Precisa: initializer/ + shared/ + integrator/__init__.py + integrator/exceptions.py (SessionStatus)
Write-Host "`n--- Packaging initializer ---"
$buildDir = Join-Path $PACKAGES "initializer_build"
if (Test-Path $buildDir) { Remove-Item -Recurse -Force $buildDir }
New-Item -ItemType Directory -Path $buildDir | Out-Null

Install-LambdaDeps -RequirementsFile $reqsInitializer -TargetDir $buildDir
Remove-Unnecessary -BuildDir $buildDir

# Código fonte
Copy-Item -Recurse -Force (Join-Path $SRC "initializer") (Join-Path $buildDir "initializer")
Copy-Item -Recurse -Force (Join-Path $SRC "shared") (Join-Path $buildDir "shared")
# Somente os arquivos necessários do integrator (para SessionStatus)
New-Item -ItemType Directory -Path (Join-Path $buildDir "integrator") | Out-Null
Copy-Item -Force (Join-Path $SRC "integrator\__init__.py") (Join-Path $buildDir "integrator\__init__.py")
Copy-Item -Force (Join-Path $SRC "integrator\exceptions.py") (Join-Path $buildDir "integrator\exceptions.py")

Write-Host "  Source: initializer/, shared/, integrator/__init__.py + exceptions.py"

# Limpar __pycache__
Get-ChildItem -Path $buildDir -Directory -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item -Recurse -Force $_.FullName }

$zipPath = Join-Path $PACKAGES "initializer.zip"
New-PosixZip -SourceDir $buildDir -ZipPath $zipPath
Remove-Item -Recurse -Force $buildDir
$size = [math]::Round((Get-Item $zipPath).Length / 1MB, 2)
Write-Host "  Done: initializer.zip ($size MB)"

# --- Integrator ---
Build-Lambda -Name "integrator" `
    -SourceDirs @("integrator", "shared") `
    -ExtraDirs @() `
    -RequirementsFile $reqsIntegrator

# --- MCP Server (inclui sample_documents) ---
Build-Lambda -Name "mcp_server" `
    -SourceDirs @("mcp_server", "shared") `
    -ExtraDirs @("sample_documents") `
    -RequirementsFile $reqsMcpServer

# Limpar requirements temp
Remove-Item -Force $reqsInitializer, $reqsIntegrator, $reqsMcpServer

Write-Host "`n=== All packages built successfully ==="
Write-Host ""
Get-ChildItem $PACKAGES -Filter "*.zip" | ForEach-Object {
    $size = [math]::Round($_.Length / 1MB, 2)
    Write-Host "  $($_.Name) - $size MB"
}
