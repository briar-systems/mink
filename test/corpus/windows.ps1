# windows system libraries, and objects and import libraries from mingw and clang-cl
# the owner runs this on a windows machine and keeps the result outside the repository
# usage: pwsh windows.ps1    (writes to $env:MINK_CORPUS and manifest/windows.tsv)
# mingw (gcc, ar, dlltool) and the clang-cl tools are used where they are on PATH,
# and anything absent is recorded as missing in the manifest

$ErrorActionPreference = 'Stop'

if (-not ($IsWindows -or $env:OS -eq 'Windows_NT')) {
    Write-Error 'windows.ps1 gathers the windows part and must run on Windows'
    exit 1
}

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$src = Join-Path $here 'src'
$corpus = if ($env:MINK_CORPUS) { $env:MINK_CORPUS } else { Join-Path $HOME '.cache/mink-corpus' }
$manifestDir = if ($env:MINK_MANIFEST_DIR) { $env:MINK_MANIFEST_DIR } else { Join-Path $here 'manifest' }
$tab = "`t"

$head = New-Object System.Collections.Generic.List[string]
$body = New-Object System.Collections.Generic.List[string]
$head.Add('# mink corpus manifest 1')
$head.Add("# part${tab}windows")
$head.Add("# host${tab}$([System.Environment]::OSVersion.VersionString)")

function Find-Tool([string]$name) {
    $found = Get-Command $name -ErrorAction SilentlyContinue
    if ($found) { return $found.Source }
    return $null
}

# first line that names a version, or missing
function Tool-Version([string]$name, [string[]]$arguments) {
    $path = Find-Tool $name
    if (-not $path) { return 'missing' }
    $lines = & $path @arguments 2>&1 | ForEach-Object { "$_" }
    $named = $lines | Where-Object { $_ -match 'version' } | Select-Object -First 1
    if ($named) { return $named }
    return ($lines | Select-Object -First 1)
}

function Note-Tool([string]$label, [string]$name, [string[]]$arguments) {
    $head.Add("# tool${tab}${label}${tab}$(Tool-Version $name $arguments)")
}

function Record([string]$path, [string]$source) {
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $corpus $path)).Hash.ToLower()
    $body.Add("${hash}${tab}$($path -replace '\\', '/')${tab}${source}")
}

function Skipped([string]$what, [string]$why) {
    $head.Add("# missing${tab}${what}${tab}${why}")
    Write-Warning "skipped $what ($why)"
}

function New-Dir([string]$path) {
    New-Item -ItemType Directory -Force -Path (Join-Path $corpus $path) | Out-Null
}

Note-Tool 'gcc' 'gcc' @('--version')
Note-Tool 'ar' 'ar' @('--version')
Note-Tool 'dlltool' 'dlltool' @('--version')
Note-Tool 'clang-cl' 'clang-cl' @('--version')
Note-Tool 'llvm-lib' 'llvm-lib' @('--version')
Note-Tool 'lib' 'lib.exe' @()
Note-Tool 'link' 'link.exe' @()
$head.Add("# windows${tab}$((Get-CimInstance Win32_OperatingSystem).Caption) $((Get-CimInstance Win32_OperatingSystem).Version)")

# system libraries straight from the installed system, pinned by the hash the manifest records
$system = @('kernel32', 'ntdll', 'user32', 'gdi32', 'advapi32', 'ucrtbase', 'msvcrt', 'shell32', 'ws2_32', 'bcrypt')
New-Dir 'windows/system'
foreach ($name in $system) {
    $file = Join-Path $env:SystemRoot "System32/$name.dll"
    if (Test-Path $file) {
        Copy-Item $file (Join-Path $corpus "windows/system/$name.dll")
        Record "windows/system/$name.dll" "System32 $name.dll $((Get-Item $file).VersionInfo.FileVersion)"
    } else {
        Skipped "system $name.dll" 'not present'
    }
}

# mingw objects and import libraries for the three windows architectures
$mingw = @(
    @{ id = 'x86_64'; gcc = 'x86_64-w64-mingw32-gcc'; dlltool = 'x86_64-w64-mingw32-dlltool'; machine = 'i386:x86-64' },
    @{ id = 'x86'; gcc = 'i686-w64-mingw32-gcc'; dlltool = 'i686-w64-mingw32-dlltool'; machine = 'i386' },
    @{ id = 'aarch64'; gcc = 'aarch64-w64-mingw32-gcc'; dlltool = 'aarch64-w64-mingw32-dlltool'; machine = 'arm64' }
)
foreach ($m in $mingw) {
    $gcc = Find-Tool $m.gcc
    if (-not $gcc) { Skipped "mingw $($m.id)" "$($m.gcc) is not on PATH"; continue }
    $version = Tool-Version $m.gcc @('--version')
    foreach ($sect in @('nofsec', 'fsec')) {
        $dir = "windows/mingw-$($m.id)/$sect"
        New-Dir $dir
        $flags = @('-O2', '-g', '-ffreestanding', '-nostdinc', "-ffile-prefix-map=$src=.")
        if ($sect -eq 'fsec') { $flags += '-ffunction-sections' }
        foreach ($name in @('basic', 'data', 'tls')) {
            Push-Location $src
            & $gcc @flags -c "$name.c" -o (Join-Path $corpus "$dir/$name.o")
            Pop-Location
            if ($LASTEXITCODE -ne 0) { throw "mingw $($m.id) $name.c failed" }
            Record "$dir/$name.o" "mingw-gcc $version $($flags -join ' ') $name.c"
        }
    }
    # an import library for kernel32 from a def file the script writes beside it
    $dlltool = Find-Tool $m.dlltool
    if ($dlltool) {
        $dir = "windows/mingw-$($m.id)/import"
        New-Dir $dir
        $def = Join-Path $corpus "$dir/corpus.def"
        "LIBRARY corpus.dll`nEXPORTS`n  sum`n  dispatch`n  mul64`n  scale`n" | Set-Content -Encoding ascii $def
        Record "$dir/corpus.def" 'written by windows.ps1'
        & $dlltool -d $def -l (Join-Path $corpus "$dir/libcorpus.dll.a") -m $m.machine
        if ($LASTEXITCODE -ne 0) { throw "dlltool $($m.id) failed" }
        Record "$dir/libcorpus.dll.a" "$($m.dlltool) $(Tool-Version $m.dlltool @('--version')) -d corpus.def -m $($m.machine)"
    } else {
        Skipped "mingw import library $($m.id)" "$($m.dlltool) is not on PATH"
    }
}

# clang-cl objects and an import library for the same three machines
$clangcl = Find-Tool 'clang-cl'
if (-not $clangcl) {
    Skipped 'clang-cl' 'clang-cl is not on PATH'
} else {
    $version = Tool-Version 'clang-cl' @('--version')
    $lib = Find-Tool 'llvm-lib'
    if (-not $lib) { $lib = Find-Tool 'lib.exe' }
    foreach ($arch in @(@{ id = 'x86_64'; target = 'x86_64-pc-windows-msvc'; machine = 'X64' },
                        @{ id = 'x86'; target = 'i686-pc-windows-msvc'; machine = 'X86' },
                        @{ id = 'aarch64'; target = 'aarch64-pc-windows-msvc'; machine = 'ARM64' })) {
        foreach ($sect in @('nofsec', 'fsec')) {
            $dir = "windows/clang-cl-$($arch.id)/$sect"
            New-Dir $dir
            # /Gy puts each function in its own comdat section, the msvc form of -ffunction-sections
            $flags = @("--target=$($arch.target)", '/O2', '/Z7', '/GS-', '/c', "/clang:-ffile-prefix-map=$src=.")
            if ($sect -eq 'fsec') { $flags += '/Gy' } else { $flags += '/Gy-' }
            foreach ($name in @('basic', 'data')) {
                Push-Location $src
                & $clangcl @flags "$name.c" "/Fo$(Join-Path $corpus "$dir/$name.obj")"
                Pop-Location
                if ($LASTEXITCODE -ne 0) { throw "clang-cl $($arch.id) $name.c failed" }
                Record "$dir/$name.obj" "clang-cl $version $($flags -join ' ') $name.c"
            }
        }
        if ($lib) {
            $dir = "windows/clang-cl-$($arch.id)/import"
            New-Dir $dir
            $def = Join-Path $corpus "$dir/corpus.def"
            "LIBRARY corpus.dll`nEXPORTS`n  sum`n  dispatch`n  mul64`n  scale`n" | Set-Content -Encoding ascii $def
            Record "$dir/corpus.def" 'written by windows.ps1'
            & $lib "/def:$def" "/machine:$($arch.machine)" "/out:$(Join-Path $corpus "$dir/corpus.lib")"
            if ($LASTEXITCODE -ne 0) { throw "lib $($arch.id) failed" }
            Record "$dir/corpus.lib" "llvm-lib or lib.exe /def:corpus.def /machine:$($arch.machine)"
        } else {
            Skipped "clang-cl import library $($arch.id)" 'neither llvm-lib nor lib.exe is on PATH'
        }
    }
}

New-Item -ItemType Directory -Force -Path $manifestDir | Out-Null
$out = Join-Path $manifestDir 'windows.tsv'
$sorted = $body | Sort-Object -Property { ($_ -split "`t")[1] } -CaseSensitive
(($head + $sorted) -join "`n") + "`n" | Set-Content -NoNewline -Encoding utf8NoBOM $out
Write-Host "corpus: windows: $($body.Count) files"
