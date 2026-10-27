# Sauvegarde de configurations réseau

Ce projet contient un script PowerShell qui se connecte à des équipements réseau
en SSH et enregistre leur configuration dans des fichiers texte. Il est conçu
pour faciliter les sauvegardes manuelles d'un petit inventaire de switches.

## Fonctionnalités

- Lit la liste des équipements depuis un fichier CSV.
- Prend en charge les plateformes `CiscoIOS` et `HP1920`.
- Utilise le nom d'utilisateur indiqué dans le CSV ou le demande s'il est absent.
- Laisse SSH demander le mot de passe dans le terminal ; le mot de passe n'est
  pas enregistré par le script.
- Accepte automatiquement la clé d'hôte lors de la première connexion et
  refuse une clé qui change ensuite (`StrictHostKeyChecking=accept-new`).
- Vérifie que la sortie contient une ligne d'identification de configuration
  avant de l'enregistrer.
- Crée un dossier par équipement, nommé avec la date, l'heure et l'adresse IP.
- Supprime les dossiers de sauvegarde datés de plus de 30 jours.
- Affiche le nombre de réussites et d'échecs à la fin de l'exécution.

## Prérequis

- Windows avec PowerShell.
- Le client OpenSSH (`ssh.exe`) disponible dans le `PATH`.
- Un accès réseau SSH aux switches et des identifiants autorisés à lire leur
  configuration.

## Inventaire CSV

Le fichier `equipements.csv`, placé à côté du script par défaut, doit contenir
les colonnes `Host` et `Platform`. Les colonnes `Name`, `User` et `Port` sont
facultatives.

Exemple avec des valeurs fictives :

```csv
"Name","Host","User","Port","Platform"
"Switch-01","192.0.2.10","admin","22","CiscoIOS"
"Switch-02","192.0.2.11","","22","HP1920"
```

Les adresses `192.0.2.x` ci-dessus sont réservées à la documentation : remplacez
ces valeurs par celles de votre propre réseau. Si `User` est vide, le script
demande le nom d'utilisateur. Si `Port` est vide, le port SSH `22` est utilisé.

## Exécution

Depuis PowerShell, dans le dossier du projet :

```powershell
.\script-save.ps1
```

Pour préciser les chemins de l'inventaire ou du dossier de sortie :

```powershell
.\script-save.ps1 -Inventory ".\equipements.csv" -BackupFolder ".\sauvegardes"
```

Les sauvegardes sont créées sous cette forme :

```text
sauvegardes\
  2026-01-31_14-30-00_192.0.2.10\
    Switch-01_192.0.2.10.txt
```

Le script retourne un code de sortie non nul si au moins une sauvegarde échoue.

## Données à ne pas publier

L'inventaire réel et les configurations sauvegardées peuvent révéler des
informations internes au réseau. Ne les publiez pas dans un dépôt partagé.
Le fichier `.gitignore` exclut `equipements.csv` et le dossier `sauvegardes`.
Utilisez uniquement des valeurs fictives dans les exemples partagés.
