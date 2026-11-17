"""Bac à sable de Jean-Eudes : essaie ici tes idées de stratégie, sans toucher aux fichiers des autres.

Ce fichier est chargé automatiquement. Une stratégie enregistrée ici apparaît dans le
simulateur et au championnat local. Exemple :

    from bot.strategy import Economy, Endgame, Plan, plan_strategy, register

    register("jean_eudes_essai", plan_strategy(Plan(economy=Economy(smithies=1, labs=2))))

Puis : python -m outils.simulation --strategie jean_eudes_essai --terrain --parties 4000 --graine 2026
"""
