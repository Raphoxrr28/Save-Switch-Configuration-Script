# Sauvegarde de configurations réseau

Ce projet contient un script PowerShell et une version Python qui se connectent
à des équipements réseau en SSH et enregistrent leur configuration dans des
fichiers texte. Ils sont conçus pour faciliter les sauvegardes manuelles d'un
petit inventaire de switches.

## Fonctionnalités

- Lit la liste des équipements depuis un fichier CSV.
- Prend en charge les plateformes `CiscoIOS`, `HP1920`, `Aruba`,
  `ArubaOS-CX`, `ArubaOS-Switch` et `HPProCurve`.
- Propose `script-save.ps1` (OpenSSH) et `script-save.py` (Netmiko).
- Utilise le nom d'utilisateur indiqué dans le CSV ou le demande s'il est absent.
- Demande le mot de passe dans le terminal sans l'afficher ; le mot de passe
  n'est pas enregistré par les scripts.
- Le script PowerShell accepte automatiquement une clé d'hôte à la première
  connexion et refuse une clé qui change ensuite
  (`StrictHostKeyChecking=accept-new`).
- Vérifie que la sortie contient une ligne d'identification de configuration
  avant de l'enregistrer.
- Crée un dossier par équipement, nommé avec la date, l'heure, le constructeur
  et l'adresse IP.
- Supprime les dossiers de sauvegarde datés de plus de 30 jours.
- Affiche le nombre de réussites et d'échecs à la fin de l'exécution.

## Prérequis

- Pour `script-save.ps1` : Windows avec PowerShell et le client OpenSSH
  (`ssh.exe`) disponible dans le `PATH`.
- Pour `script-save.py` : Python 3 et Netmiko, installable avec
  `python -m pip install -r requirements.txt`.
- Un accès réseau SSH aux switches et des identifiants autorisés à lire leur
  configuration.

## Inventaire CSV

Le fichier `equipements.csv`, placé à côté du script par défaut, doit contenir
les colonnes `Host` et `Platform`. Les colonnes `Name`, `User` et `Port` sont
facultatives. Pour Aruba, utilisez `Aruba` si vous ne connaissez pas la famille,
ou indiquez `ArubaOS-CX` ou `ArubaOS-Switch`. Pour HP ProCurve, indiquez
`HPProCurve`.

Exemple avec des valeurs fictives :

```csv
"Name","Host","User","Port","Platform"
"Switch-01","192.0.2.10","admin","22","CiscoIOS"
"Switch-02","192.0.2.11","","22","Aruba"
"Switch-03","192.0.2.12","admin","22","HPProCurve"
```

Les adresses `192.0.2.x` ci-dessus sont réservées à la documentation : remplacez
ces valeurs par celles de votre propre réseau. Si `User` est vide, le script
demande le nom d'utilisateur. Si `Port` est vide, le port SSH `22` est utilisé.

## Exécution

### Version PowerShell

Depuis PowerShell, dans le dossier du projet :

```powershell
.\script-save.ps1
```

Pour préciser les chemins de l'inventaire ou du dossier de sortie :

```powershell
.\script-save.ps1 -Inventory ".\equipements.csv" -BackupFolder ".\sauvegardes"
```

Pour lancer les sauvegardes en boucle, toutes les 10 minutes après la fin de
chaque exécution :

```powershell
.\script-save-loop.ps1
```

Le lanceur démarre une sauvegarde immédiatement, puis attend 10 minutes après
chaque exécution avant de recommencer. Il reste ouvert dans le terminal ;
appuyez sur `Ctrl+C` pour l'arrêter. Comme le script de sauvegarde demande le
mot de passe SSH, il faudra le saisir à chaque cycle. Ne fermez pas le terminal
pendant une sauvegarde. Ce lanceur appelle `script-save.ps1` (et non la version
Python) et doit rester dans une session PowerShell interactive pour que les
invites SSH puissent être saisies.

### Version Python avec Netmiko

Installez d'abord Netmiko :

```powershell
python -m pip install -r requirements.txt
```

Puis lancez le script :

```powershell
python .\script-save.py
```

Pour préciser les chemins :

```powershell
python .\script-save.py --inventory ".\equipements.csv" --backup-folder ".\sauvegardes"
```

La version Python demande le mot de passe sans l'afficher. Elle vérifie les clés
hôtes SSH avec le fichier `known_hosts` de l'utilisateur : la clé de chaque
switch doit donc y être approuvée avant la connexion. Le profil `Aruba` générique
utilise le pilote Netmiko ArubaOS-Switch ; choisissez `ArubaOS-CX` pour les
switches Aruba CX.

Les sauvegardes sont créées sous cette forme :

```text
sauvegardes\
  2026-01-31_14-30-00_Aruba_192.0.2.11\
    Switch-02_192.0.2.11.txt
```

Le nom du constructeur dans le dossier est `Cisco`, `Aruba` ou `HP`.

Les familles Aruba et ProCurve couvrent plusieurs modèles et versions de
firmware. Le script PowerShell utilise les commandes CLI courantes `no page`
et `show running-config` pour ces profils ; Netmiko s'appuie sur le pilote
correspondant pour préparer la session, puis lance `show running-config`.
Cela ne garantit pas la compatibilité avec tous les produits ni toutes les
versions. Les équipements Aruba Instant On ou les interfaces sans CLI SSH
peuvent nécessiter une autre méthode. Vérifiez une sauvegarde complète sur
chaque famille et version avant de vous y fier en production. Le pilote Netmiko
ArubaOS-CX est indiqué comme expérimental par le projet Netmiko et demande une
validation particulière sur le modèle et le firmware utilisés.

Le script retourne un code de sortie non nul si au moins une sauvegarde échoue.

## Données à ne pas publier

L'inventaire réel et les configurations sauvegardées peuvent révéler des
informations internes au réseau. Ne les publiez pas dans un dépôt partagé.
Le fichier `.gitignore` exclut `equipements.csv` et le dossier `sauvegardes`.
Utilisez uniquement des valeurs fictives dans les exemples partagés.
