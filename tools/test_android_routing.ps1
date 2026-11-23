$ErrorActionPreference='Stop'
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$taskCache=Join-Path $taskRoot '.build'
$taskJdk='C:\Program Files\Android\openjdk\jdk-21.0.8'
$taskAndroidJar=(Get-ChildItem -LiteralPath (Join-Path $taskCache 'android-platform') -Filter android.jar -Recurse | Select-Object -First 1).FullName
$taskJson=Join-Path $taskCache 'json-tests.jar'
if (!(Test-Path -LiteralPath $taskJson)) {
    Invoke-WebRequest -Uri 'https://repo.maven.apache.org/maven2/org/json/json/20240303/json-20240303.jar' -OutFile $taskJson
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $taskJson).Hash -ne '3CF6CD6892E32E2B4C1C39E0F52F5248A2F5B37646FDFBB79A66B46B618414ED') {throw 'Dependencia JSON de pruebas no verificada.'}
$taskClasses=Join-Path $taskCache 'android-routing-tests'
New-Item -ItemType Directory -Force -Path $taskClasses | Out-Null
$taskSources=@((Join-Path $taskRoot 'android\src\com\jad\print\ServerConnection.java'),(Join-Path $taskRoot 'tests\android\ServerConnectionTest.java'))
& "$taskJdk\bin\javac.exe" -encoding UTF-8 -classpath "$taskAndroidJar;$taskJson" -d $taskClasses @taskSources
if ($LASTEXITCODE -ne 0) {throw 'Falló la compilación de pruebas de conexión Android.'}
& "$taskJdk\bin\java.exe" -classpath "$taskClasses;$taskJson;$taskAndroidJar" com.jad.print.ServerConnectionTest
if ($LASTEXITCODE -ne 0) {throw 'Fallaron las pruebas de conexión Android.'}
