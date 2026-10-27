# Lance script-save.ps1 immédiatement, puis recommence 10 minutes après
# la fin de chaque exécution. Arrêter la boucle avec Ctrl+C.
$ErrorActionPreference = 'Stop'

$backupScript = Join-Path $PSScriptRoot 'script-save.ps1'
if (-not (Test-Path -LiteralPath $backupScript -PathType Leaf)) {
    throw "Script de sauvegarde introuvable : $backupScript"
}

$powerShellExe = (Get-Command powershell.exe -ErrorAction Stop).Source
$intervalSeconds = 600

Write-Information "Lancement périodique de $backupScript (intervalle : 10 minutes)." -InformationAction Continue
Write-Information 'La prochaine exécution commencera 10 minutes après la fin de la précédente.' -InformationAction Continue
Write-Information 'Appuyez sur Ctrl+C pour arrêter.' -InformationAction Continue

while ($true) {
    $startTime = Get-Date
    Write-Information "Début de la sauvegarde : $($startTime.ToString('yyyy-MM-dd HH:mm:ss'))" -InformationAction Continue

    try {
        # Un processus PowerShell séparé permet au script appelé de retourner
        # son code de sortie sans arrêter cette boucle. Il peut demander le mot
        # de passe dans le même terminal.
        & $powerShellExe -NoProfile -File $backupScript
        $exitCode = $LASTEXITCODE

        if ($exitCode -eq 0) {
            Write-Information 'Exécution terminée sans échec.' -InformationAction Continue
        }
        else {
            Write-Warning "Le script de sauvegarde s'est terminé avec le code $exitCode."
        }
    }
    catch {
        Write-Warning "Impossible d'exécuter le script de sauvegarde : $($_.Exception.Message)"
    }

    $nextRun = (Get-Date).AddSeconds($intervalSeconds)
    Write-Information "Prochaine exécution au plus tôt : $($nextRun.ToString('yyyy-MM-dd HH:mm:ss'))" -InformationAction Continue
    Start-Sleep -Seconds $intervalSeconds
}
