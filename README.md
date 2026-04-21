## SI‑SEP Commune

### Configuration email (SMTP) — obligatoire
Le projet est configuré pour **envoyer uniquement de vrais emails** (pas d’email en console).

1) Créez un fichier `.env` à la racine (copiez `.env.example`).
2) Renseignez :
   - `SMTP_USERNAME` (votre Gmail)
   - `SMTP_PASSWORD` (**mot de passe d’application** Gmail)

Gmail nécessite d’activer la **validation en 2 étapes**, puis de générer un **mot de passe d’application**.

### Démarrage (PowerShell)
Chargez les variables puis lancez Django. Exemple simple :

```powershell
Get-Content .env | ForEach-Object {
  if ($_ -match '^[A-Za-z_][A-Za-z0-9_]*=') {
    $k,$v = $_ -split '=',2
    $env:$k = $v.Trim('\"')
  }
}
python manage.py runserver
```

