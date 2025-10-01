# Template CAPSYS - Banc de Test

## Vue d'ensemble

Ce template fournit une structure complète pour créer des bancs de test automatisés avec interface graphique PyQt6. Il est conçu pour exécuter des séquences de tests sur des dispositifs, enregistrer les résultats en base de données MySQL et générer des rapports PDF. Il doit être utilisé avec la base de données Capsys.

## Architecture du projet

```
capsys_bdt_template/
├── template.py              # Application principale avec interface PyQt6
├── configuration.py         # Configuration globale et paramètres
├── init_submodules.py      # Script de mise à jour des submodules Git
├── assets/                 # Ressources graphiques et fichiers statiques
│   ├── dark_theme.css     # Thème sombre pour l'interface
│   └── logo-big.png       # Logo de l'application
├── modules/               # Modules réutilisables
|   └── capsys_alim_ka3005p   # Gestionnaire alimentation KA3005P
|   └── capsys_daq_manager    # Gestionnaire des DAQ-NI
|   └── capsys_mcp23017       # Gestionnaire des MCP23017
│   ├── capsys_mysql_command  # Gestionnaire de base de données MySQL
│   └── capsys_pdf_report     # Générateur de rapports PDF
└── steps/                 # Étapes de test organisées par numéro
    ├── s01/              # Première étape (initialisation)
    ├── s02/, s03/, ...   # Étapes suivantes à créer
    └── zz/               # Étape finale (nettoyage)
```

## Guide du développeur

### Prérequis
- Python 3.13+
- MySQL Server avec bdd Capsys
- Git (pour les submodules)

### Initialiser les submodules
```bash
python init_submodules.py
```

### Fonctionnement
- Gestion des variables globales autour de la classe AppConfig de configuration.py
- Gestion de l'interface graphique directement via template.py avec :
    - Chargement dynamique des étapes depuis le dossier `steps/`
    - Étapes numérotées (s01, s02, s03...) exécutées dans l'ordre
    - Étape finale `zz/fin_du_test.py` toujours exécutée en dernier
    - Chaque étape doit implémenter :
        - `run_step(log, config)` : fonction principale d'exécution
        - `get_info()` : description de l'étape (optionnel)

### Développement d'un nouveau banc de test

#### 1. Configuration du projet
Modifier le fichier `configuration.py` :
```python
class Arg:
    name = "MON_BANC_DE_TEST"  # Nom du banc
    operator = "Prénom NOM"    # Opérateur par défaut
    # Paramètres de base de données
    user = "root"
    password = "motdepasse"
    host = "127.0.0.1"
    database = "ma_base_test"
    # Autres paramètres spécifiques...
```

#### 2. Accès à la base de données
```python
# Créer un enregistrement
config.db.create("table_name", {"field": "value"})

# Lire des données
data = config.db.read("table_name", {"condition": "value"})

# Mettre à jour
config.db.update_by_id("table_name", id, {"field": "new_value"})
```

### Bonnes pratiques

1. **Nommage des étapes** : Utiliser le format `sXX` (s01, s02, etc.) pour les étapes numérotées
2. **Gestion des erreurs** : Toujours encapsuler le code dans try/except
3. **Logs descriptifs** : Utiliser des messages clairs avec les bonnes couleurs
4. **Base de données** : Enregistrer systématiquement le nom de l'étape
5. **Tests indépendants** : Chaque étape doit pouvoir être exécutée indépendamment
6. **Documentation** : Implémenter `get_info()` pour décrire chaque étape

### Débogage

- Activer `show_all_logs = True` dans `configuration.py` pour plus de détails
- Vérifier les logs de la console pour identifier les problèmes
- Utiliser la base de données pour tracer l'historique des tests

### Extension du template

Le template est conçu pour être extensible :
- Ajouter de nouveaux modules dans `modules/`
- Personnaliser l'interface dans `template.py`
- Modifier les rapports via `capsys_pdf_report`
- Adapter la configuration selon vos besoins

---

**Auteur** : Thomas GERARDIN  
**Version** : 1.0