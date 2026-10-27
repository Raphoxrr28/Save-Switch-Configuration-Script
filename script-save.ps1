# Sauvegarde la configuration de chaque équipement listé dans le fichier CSV.
# Exemple d'utilisation :
#   .\script-save.ps1
#   .\script-save.ps1 -Inventory ".\equipements.csv" -BackupFolder ".\sauvegardes"
param(
    # Fichier CSV contenant au minimum les colonnes Host et Platform.
    # Name, User et Port sont facultatives.
    [string]$Inventory = "$PSScriptRoot\equipements.csv",

    # Dossier dans lequel les sauvegardes seront créées.
    [string]$BackupFolder = "$PSScriptRoot\sauvegardes"
)

# Arrête le script sur les erreurs PowerShell non gérées.
$ErrorActionPreference = 'Stop'

# Charge l'inventaire et vérifie qu'il contient des équipements et les colonnes requises.
$devices = @(Import-Csv -Path $Inventory)
if ($devices.Count -eq 0) { throw "Inventaire vide : $Inventory" }
if (@('Host', 'Platform') | Where-Object { $_ -notin $devices[0].PSObject.Properties.Name }) {
    throw 'Le CSV doit contenir les colonnes Host et Platform.'
}

# Supprime les anciens dossiers de sauvegarde datés de plus de 30 jours.
# Le nom du dossier commence par la date, éventuellement suivie de l'adresse IP.
$cutoff = (Get-Date).AddDays(-30)
if (Test-Path -LiteralPath $BackupFolder -PathType Container) {
    foreach ($oldBackup in Get-ChildItem -LiteralPath $BackupFolder -Directory) {
        $backupDate = [datetime]::MinValue
        $datePart = if ($oldBackup.Name -match '^(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})(?:_|$)') {
            $Matches[1]
        }
        $isDatedBackup = [datetime]::TryParseExact(
            $datePart,
            'yyyy-MM-dd_HH-mm-ss',
            [Globalization.CultureInfo]::InvariantCulture,
            [Globalization.DateTimeStyles]::None,
            [ref]$backupDate
        )
        if ($isDatedBackup -and $backupDate -lt $cutoff -and
            -not ($oldBackup.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            Remove-Item -LiteralPath $oldBackup.FullName -Recurse -Force
            Write-Information "[SUPPRIME] Sauvegarde de plus de 30 jours : $($oldBackup.Name)" -InformationAction Continue
        }
    }
}

# Utilise la même date et heure pour nommer les dossiers créés pendant cette exécution.
$runTimestamp = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
$successCount = 0
$failureDetails = @()

# Traite les équipements un par un afin qu'un échec n'empêche pas les autres sauvegardes.
foreach ($device in $devices) {
    # Utilise le nom du switch si disponible, sinon son adresse IP.
    $name = if ($device.Name) { $device.Name } else { $device.Host }
    $port = if ($device.Port) { $device.Port } else { '22' }

    try {
        # Utilise l'utilisateur du CSV ou le demande s'il n'est pas renseigné.
        # SSH demandera le mot de passe dans le terminal ; celui-ci n'est pas enregistré.
        $user = if ([string]::IsNullOrWhiteSpace($device.User)) {
            Read-Host "Utilisateur SSH pour $name"
        } else {
            $device.User.Trim()
        }
        if ([string]::IsNullOrWhiteSpace($user)) {
            throw "Le nom d'utilisateur SSH ne peut pas être vide."
        }

        # Prépare les commandes adaptées à la plateforme, le constructeur à afficher
        # dans le dossier, et un motif de contrôle de la configuration reçue.
        $platform = if ($device.Platform) { $device.Platform.Trim() } else { 'CiscoIOS' }
        switch ($platform.ToLowerInvariant()) {
            'ciscoios' {
                $manufacturer = 'Cisco'
                $commands = "terminal length 0`nshow running-config`nexit"
                $expectedConfigPattern = '(?im)^\s*hostname\s+\S+'
            }
            'hp1920' {
                $manufacturer = 'HP'
                $commands = "_cmdline-mode on`ny`nscreen-length disable`ndisplay current-configuration`nquit"
                $expectedConfigPattern = '(?im)^\s*sysname\s+\S+'
            }
            'aruba' {
                $manufacturer = 'Aruba'
                $commands = "no page`nshow running-config`nexit"
                $expectedConfigPattern = '(?im)^\s*(?:hostname\s+\S+|;\s*.*configuration editor)'
            }
            'arubaos-cx' {
                $manufacturer = 'Aruba'
                $commands = "no page`nshow running-config`nexit"
                $expectedConfigPattern = '(?im)^\s*(?:hostname\s+\S+|;\s*.*configuration editor)'
            }
            { $_ -in 'arubaos-switch', 'hpprocurve' } {
                $manufacturer = if ($platform.ToLowerInvariant() -eq 'hpprocurve') { 'HP' } else { 'Aruba' }
                $commands = "no page`nshow running-config`nexit"
                $expectedConfigPattern = '(?im)^\s*(?:hostname\s+\S+|;\s*.*configuration editor)'
            }
            default { throw "Plateforme non prise en charge : $platform" }
        }

        # Lance SSH en mode interactif pour permettre la saisie du mot de passe.
        # accept-new enregistre automatiquement une nouvelle clé hôte, mais refuse
        # une clé qui aurait changé depuis une connexion précédente.
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            $config = $commands | & ssh.exe -tt -o BatchMode=no -o StrictHostKeyChecking=accept-new `
                -p $port "$user@$($device.Host)"
            $sshExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }

        # Refuse d'enregistrer un résultat si SSH a échoué ou si la réponse
        # ne ressemble pas à la configuration attendue pour cette plateforme.
        if ($sshExitCode -ne 0 -or -not $config) {
            throw 'Connexion SSH echouee ou configuration vide.'
        }
        $configText = $config -join "`n"
        if ($configText -notmatch $expectedConfigPattern) {
            throw "La sortie SSH ne contient pas la configuration attendue pour $platform."
        }

        # Crée un dossier par équipement, nommé avec la date/heure, le constructeur
        # et l'adresse IP,
        # puis écrit la configuration dans un fichier texte à l'intérieur.
        $safeHost = $device.Host -replace '[<>:"/\\|?*]', '_'
        $deviceFolder = Join-Path $BackupFolder ($runTimestamp + '_' + $manufacturer + '_' + $safeHost)
        New-Item -ItemType Directory -Path $deviceFolder -Force | Out-Null
        $file = (($name -replace '[<>:"/\\|?*]', '_') + '_' + $safeHost + '.txt')
        $config | Out-File -FilePath (Join-Path $deviceFolder $file) -Encoding utf8
        Write-Information "[OK] $name : $deviceFolder" -InformationAction Continue
        $successCount++
    }
    catch {
        # Mémorise l'échec et continue avec l'équipement suivant.
        $errorMessage = $_.Exception.Message
        Write-Warning "[ECHEC] $name : $errorMessage"
        $failureDetails += [pscustomobject]@{
            Name  = $name
            Error = $errorMessage
        }
    }
}

# Affiche le résumé global et retourne un code d'erreur si au moins un équipement a échoué.
Write-Information "Sauvegardes dans : $BackupFolder" -InformationAction Continue
Write-Information "Bilan : $successCount réussite(s), $($failureDetails.Count) échec(s) sur $($devices.Count)." -InformationAction Continue
foreach ($failure in $failureDetails) {
    Write-Information " - $($failure.Name) : $($failure.Error)" -InformationAction Continue
}
if ($failureDetails.Count -gt 0) { exit 1 }
