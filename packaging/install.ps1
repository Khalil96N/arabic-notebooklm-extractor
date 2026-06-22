$ErrorActionPreference = "Stop"

$installDir = Join-Path $env:LOCALAPPDATA "Programs\NotebookLMExtractor"
$archive = Join-Path $PSScriptRoot "NotebookLMExtractor.zip"

if (-not (Test-Path -LiteralPath $archive)) {
    throw "The application archive is missing."
}

if (Test-Path -LiteralPath $installDir) {
    $resolvedInstall = [System.IO.Path]::GetFullPath($installDir)
    $allowedRoot = [System.IO.Path]::GetFullPath(
        (Join-Path $env:LOCALAPPDATA "Programs")
    )
    if (-not $resolvedInstall.StartsWith(
        $allowedRoot,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Refusing to replace an unexpected installation path."
    }
    Remove-Item -LiteralPath $resolvedInstall -Recurse -Force
}

New-Item -ItemType Directory -Path $installDir -Force | Out-Null
Expand-Archive -LiteralPath $archive -DestinationPath $installDir -Force

$exe = Join-Path $installDir "NotebookLMExtractor.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    throw "The installed executable was not found."
}

$shell = New-Object -ComObject WScript.Shell
$desktopShortcut = Join-Path (
    [Environment]::GetFolderPath("Desktop")
) "NotebookLM Extractor.lnk"
$startMenuDir = Join-Path (
    [Environment]::GetFolderPath("Programs")
) "NotebookLM Extractor"
New-Item -ItemType Directory -Path $startMenuDir -Force | Out-Null
$startMenuShortcut = Join-Path $startMenuDir "NotebookLM Extractor.lnk"

foreach ($shortcutPath in @($desktopShortcut, $startMenuShortcut)) {
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $exe
    $shortcut.WorkingDirectory = $installDir
    $shortcut.Description = "NotebookLM Arabic Lecture Extractor"
    $shortcut.IconLocation = "$exe,0"
    $shortcut.Save()
}

$chromePaths = @(
    (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe")
)
$chromeInstalled = $chromePaths | Where-Object {
    $_ -and (Test-Path -LiteralPath $_)
}

if (-not $chromeInstalled) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show(
        "The app is installed, but Google Chrome is required.",
        "NotebookLM Extractor"
    ) | Out-Null
}
