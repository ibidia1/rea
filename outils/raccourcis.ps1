# L'icone "Reanimation" du Bureau, et la meme dans le menu Demarrer.
#
# En PowerShell et non en .bat, pour une raison precise : le Bureau n'est pas
# toujours dans %USERPROFILE%\Desktop. Des qu'un poste a OneDrive - et celui
# du service en a un - le Bureau est redirige, et une icone posee a l'ancienne
# adresse n'apparait nulle part. Seul Windows sait ou il est, et c'est
# [Environment]::GetFolderPath qui le lui demande.
#
# Aucun accent dans ce fichier, comme dans les .bat : Windows PowerShell 5.1
# lit un .ps1 sans BOM avec la page de codes ANSI, pas en UTF-8. Les accents
# y arriveraient abimes.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File raccourcis.ps1 `
#       -Programme "C:\ReaService\programme"

param(
    [Parameter(Mandatory = $true)][string]$Programme
)

$ErrorActionPreference = 'Stop'

# Deux facons de lancer EXACTEMENT la meme application, deux icones :
#
#   "Reanimation - Local"    poste isole, joignable de ce PC seulement.
#   "Reanimation - Serveur"  ce PC sert la reanimation au reseau (auto).
#
# On ne touche pas au code ni aux donnees : seules les icones different, par
# le .bat qu'elles appellent.
$modes = @(
    @{ Nom = 'Reanimation - Local';   Bat = 'lancer_reanimation_local.bat';
       Desc = 'Reanimation polyvalente - poste local (ce PC uniquement)';
       Icone = 171 }
    @{ Nom = 'Reanimation - Serveur'; Bat = 'lancer_reanimation_serveur.bat';
       Desc = 'Reanimation polyvalente - serveur du reseau local';
       Icone = 18 }
)

foreach ($mode in $modes) {
    $cible = Join-Path $Programme $mode.Bat
    if (-not (Test-Path -LiteralPath $cible)) {
        Write-Host "  $($mode.Bat) est introuvable dans $Programme"
        exit 1
    }
}

$cree = @()

foreach ($nom in @('Desktop', 'Programs')) {
    $dossier = [Environment]::GetFolderPath($nom)
    if ([string]::IsNullOrWhiteSpace($dossier)) { continue }
    if (-not (Test-Path -LiteralPath $dossier)) { continue }

    # L'ancienne icone unique "Reanimation.lnk", si elle traine d'une
    # installation precedente : on la retire pour ne pas laisser trois icones
    # dont une qui prete a confusion.
    $ancienne = Join-Path $dossier 'Reanimation.lnk'
    if (Test-Path -LiteralPath $ancienne) { Remove-Item -LiteralPath $ancienne -Force }

    $shell = New-Object -ComObject WScript.Shell
    foreach ($mode in $modes) {
        $lien = $shell.CreateShortcut((Join-Path $dossier ($mode.Nom + '.lnk')))
        $lien.TargetPath = Join-Path $Programme $mode.Bat
        $lien.WorkingDirectory = $Programme
        $lien.Description = $mode.Desc
        # Une icone de Windows plutot qu'un fichier livre : rien a copier, et
        # elle survit a un deplacement du dossier.
        $lien.IconLocation = "$env:SystemRoot\System32\shell32.dll,$($mode.Icone)"
        $lien.Save()
        $cree += $lien.FullName
    }
}

if ($cree.Count -eq 0) {
    Write-Host '  Aucun emplacement de raccourci trouve.'
    exit 1
}

foreach ($chemin in $cree) { Write-Host "  Icone : $chemin" }
exit 0
