# Trouve l'adresse IPv4 de ce PC sur le reseau local, et l'ecrit, seule, sur
# la sortie standard. Rien d'autre n'est ecrit : le launcher serveur la lit
# telle quelle. Si aucune adresse utilisable n'est trouvee, ce script n'ecrit
# rien et le launcher retombe sur son propre repli.
#
# Aucune IP n'est codee en dur : on prend celle de la carte qui porte la
# passerelle par defaut (celle qui parle au reseau), en ecartant la boucle
# locale (127.x) et les adresses d'auto-configuration (169.254.x, celles que
# Windows se donne quand il n'a PAS de reseau).
#
# Aucun accent dans ce fichier, comme les .bat et raccourcis.ps1 : Windows
# PowerShell 5.1 lit un .ps1 sans BOM en page de codes ANSI, pas en UTF-8.

$ErrorActionPreference = 'SilentlyContinue'

function Est-Adresse-Utilisable($ip) {
    if ([string]::IsNullOrWhiteSpace($ip)) { return $false }
    if ($ip -eq '0.0.0.0' -or $ip -eq '127.0.0.1') { return $false }
    if ($ip -like '169.254.*') { return $false }   # auto-config : pas de reseau
    return $true
}

$adresse = $null

# 1. La bonne source : la carte "Up" qui a une passerelle par defaut. C'est
#    celle par laquelle ce PC est joignable depuis les autres postes.
try {
    $adresse = Get-NetIPConfiguration |
        Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } |
        ForEach-Object { $_.IPv4Address.IPAddress } |
        Where-Object { Est-Adresse-Utilisable $_ } |
        Select-Object -First 1
} catch { }

# 2. Repli, si la commande precedente n'existe pas (vieux Windows) ou ne rend
#    rien : on ouvre un socket vers une adresse quelconque et on lit l'adresse
#    locale que le systeme choisit pour l'atteindre. Aucun paquet n'est envoye
#    (UDP), et cela marche sans Internet du moment qu'il y a une passerelle.
if (-not $adresse) {
    try {
        $s = New-Object System.Net.Sockets.Socket(
            [System.Net.Sockets.AddressFamily]::InterNetwork,
            [System.Net.Sockets.SocketType]::Dgram,
            [System.Net.Sockets.ProtocolType]::Udp)
        $s.Connect('8.8.8.8', 80)
        $candidat = $s.LocalEndPoint.Address.ToString()
        $s.Close()
        if (Est-Adresse-Utilisable $candidat) { $adresse = $candidat }
    } catch { }
}

# 3. Dernier repli : la premiere IPv4 privee trouvee sur une carte active.
if (-not $adresse) {
    try {
        $adresse = Get-NetIPAddress -AddressFamily IPv4 |
            Where-Object { Est-Adresse-Utilisable $_.IPAddress } |
            Where-Object {
                $_.IPAddress -like '192.168.*' -or
                $_.IPAddress -like '10.*' -or
                $_.IPAddress -match '^172\.(1[6-9]|2[0-9]|3[0-1])\.'
            } |
            Select-Object -First 1 -ExpandProperty IPAddress
    } catch { }
}

if ($adresse) { Write-Output $adresse }
