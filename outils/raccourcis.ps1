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

$cible = Join-Path $Programme 'lancer_reanimation.bat'
if (-not (Test-Path -LiteralPath $cible)) {
    Write-Host "  lancer_reanimation.bat est introuvable dans $Programme"
    exit 1
}

$cree = @()

foreach ($nom in @('Desktop', 'Programs')) {
    $dossier = [Environment]::GetFolderPath($nom)
    if ([string]::IsNullOrWhiteSpace($dossier)) { continue }
    if (-not (Test-Path -LiteralPath $dossier)) { continue }

    $shell = New-Object -ComObject WScript.Shell
    $lien = $shell.CreateShortcut((Join-Path $dossier 'Reanimation.lnk'))
    $lien.TargetPath = $cible
    $lien.WorkingDirectory = $Programme
    $lien.Description = 'Logiciel de service - Reanimation polyvalente'
    # Une icone de Windows plutot qu'un fichier livre : rien a copier, et
    # elle survit a un deplacement du dossier.
    $lien.IconLocation = "$env:SystemRoot\System32\shell32.dll,171"
    $lien.Save()
    $cree += $lien.FullName
}

if ($cree.Count -eq 0) {
    Write-Host '  Aucun emplacement de raccourci trouve.'
    exit 1
}

foreach ($chemin in $cree) { Write-Host "  Icone : $chemin" }
exit 0
