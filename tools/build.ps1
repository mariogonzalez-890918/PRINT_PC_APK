param([switch]$WindowsOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$cacheRoot = Join-Path $projectRoot '.build'
$jdkRoot = 'C:\Program Files\Android\openjdk\jdk-21.0.8'
$buildTools = Join-Path $cacheRoot 'android-tools\android-15'
$androidJar = Join-Path $cacheRoot 'android-platform\android-35\android.jar'
if (!$WindowsOnly -and !(Test-Path -LiteralPath $androidJar)) {
    $androidJar = (Get-ChildItem -LiteralPath (Join-Path $cacheRoot 'android-platform') -Filter android.jar -Recurse | Select-Object -First 1).FullName
}
$env:JAVA_HOME = $jdkRoot
$env:PATH = "$jdkRoot\bin;$env:PATH"
function Run-Checked([string]$program,[string[]]$arguments) {
    & $program @arguments
    if ($LASTEXITCODE -ne 0) { throw "Falló $program (código $LASTEXITCODE)" }
}
$distRoot = Join-Path $projectRoot 'dist'
$androidBuild = Join-Path $cacheRoot 'apk'
New-Item -ItemType Directory -Force -Path $distRoot,$androidBuild,(Join-Path $androidBuild 'classes'),(Join-Path $androidBuild 'dex') | Out-Null
if (!$WindowsOnly) {
Run-Checked "$buildTools\aapt2.exe" @('compile','--dir',"$projectRoot\android\res",'-o',"$androidBuild\resources.zip")
Run-Checked "$buildTools\aapt2.exe" @('link','-o',"$androidBuild\unsigned.apk",'-I',$androidJar,'--manifest',"$projectRoot\android\AndroidManifest.xml",'--version-code','4','--version-name','0.4.0',"$androidBuild\resources.zip")
$javaSources = @(Get-ChildItem -LiteralPath "$projectRoot\android\src" -Filter *.java -Recurse | ForEach-Object { $_.FullName })
Run-Checked "$jdkRoot\bin\javac.exe" (@('-encoding','UTF-8','--release','8','-classpath',$androidJar,'-d',"$androidBuild\classes") + $javaSources)
Run-Checked "$jdkRoot\bin\jar.exe" @('cf',"$androidBuild\classes.jar",'-C',"$androidBuild\classes",'.')
Run-Checked "$buildTools\d8.bat" @('--min-api','26','--lib',$androidJar,'--output',"$androidBuild\dex","$androidBuild\classes.jar")
Run-Checked "$jdkRoot\bin\jar.exe" @('uf',"$androidBuild\unsigned.apk",'-C',"$androidBuild\dex",'classes.dex')
Run-Checked "$buildTools\zipalign.exe" @('-f','4',"$androidBuild\unsigned.apk","$androidBuild\aligned.apk")
# The signing key stays local and is never placed in an installer or source archive.
$keyRoot = Join-Path $env:LOCALAPPDATA 'JADPrint\signing'
New-Item -ItemType Directory -Force -Path $keyRoot | Out-Null
$keyFile = Join-Path $keyRoot 'android.jks'
$passwordFile = Join-Path $keyRoot 'password.txt'
if (!(Test-Path -LiteralPath $keyFile)) {
    $random = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($random)
    [Convert]::ToBase64String($random) | Set-Content -LiteralPath $passwordFile -Encoding ascii -NoNewline
    Run-Checked "$jdkRoot\bin\keytool.exe" @('-genkeypair','-keystore',$keyFile,'-storepass:file',$passwordFile,'-keypass:file',$passwordFile,'-alias','jadprint','-keyalg','RSA','-keysize','3072','-validity','10000','-dname','CN=JAD Print Local, O=JAD, C=MX')
}
Run-Checked "$buildTools\apksigner.bat" @('sign','--ks',$keyFile,'--ks-key-alias','jadprint','--ks-pass',"file:$passwordFile",'--out',"$distRoot\PRINTER-TAB-Android-0.4.0.apk","$androidBuild\aligned.apk")
Run-Checked "$buildTools\apksigner.bat" @('verify','--verbose',"$distRoot\PRINTER-TAB-Android-0.4.0.apk")
Run-Checked "$buildTools\aapt2.exe" @('dump','badging',"$distRoot\PRINTER-TAB-Android-0.4.0.apk")

}

$packageRoot = Join-Path $cacheRoot 'package'
New-Item -ItemType Directory -Force -Path $packageRoot,(Join-Path $packageRoot 'runtime'),(Join-Path $packageRoot 'pc'),(Join-Path $packageRoot 'engine') | Out-Null
Copy-Item -Path "$cacheRoot\python\*" -Destination "$packageRoot\runtime" -Recurse -Force
# Embedded Python adds this explicit directory to sys.path for application modules.
@('python313.zip','.','..\pc','import site') | Set-Content -LiteralPath "$packageRoot\runtime\python313._pth" -Encoding ascii
Copy-Item -Path "$projectRoot\pc\*.py","$projectRoot\pc\*.html","$projectRoot\pc\*.js","$projectRoot\pc\*.svg","$projectRoot\pc\*.ico","$projectRoot\pc\*.png" -Destination "$packageRoot\pc" -Force
if (Test-Path -LiteralPath "$packageRoot\JADPrint.exe") { Remove-Item -LiteralPath "$packageRoot\JADPrint.exe" -Force }
$sumatraExe = Get-ChildItem -LiteralPath "$cacheRoot\sumatra" -Filter '*.exe' | Select-Object -First 1
Copy-Item -LiteralPath $sumatraExe.FullName -Destination "$packageRoot\engine\SumatraPDF.exe" -Force
Copy-Item -LiteralPath "$cacheRoot\sumatra\COPYING" -Destination "$packageRoot\engine\COPYING" -Force
Run-Checked 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe' @('/nologo','/target:winexe','/reference:System.Windows.Forms.dll','/reference:System.Drawing.dll','/reference:System.Web.Extensions.dll',"/win32icon:$projectRoot\pc\app.ico","/out:$packageRoot\PRINTER-TAB.exe","$projectRoot\tools\Launcher.cs")
Run-Checked "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" @('/Q',"$projectRoot\tools\installer.iss")
Get-FileHash -Algorithm SHA256 -LiteralPath "$distRoot\PRINTER-TAB-Android-0.4.0.apk","$distRoot\PRINTER-TAB-Instalador-0.4.0.exe" | Format-List
