# Contribution

## Workflow

1. Creer une branche courte et explicite.
2. Faire une modification limitee a un sujet.
3. Lancer les controles locaux.
4. Ouvrir une pull request avec le contexte, les changements et les tests.

## Controles locaux

```powershell
ruff check .
pytest
```

## Style

- Python 3.12 minimum.
- Code type-hinte quand c'est utile.
- Une classe ou fonction doit avoir une responsabilite claire.
- Les secrets restent dans `.env` ou dans des variables d'environnement.
- Les exemples de configuration doivent utiliser des valeurs fictives.
