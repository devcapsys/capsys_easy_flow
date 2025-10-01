# -*- coding: utf-8 -*-
"""
Gestionnaire de version
Gère la mise à jour du hash Git et la remise à DEBUG
"""

import subprocess
import sys
import os
import re
import argparse


def run_git_command(command):
    """Exécute une commande git et retourne le résultat"""
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True, 
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        if result.returncode != 0:
            print(f"Erreur lors de l'exécution de la commande git: {command}")
            print(f"Erreur: {result.stderr}")
            return None
        return result.stdout.strip()
    except Exception as e:
        print(f"Erreur lors de l'exécution de la commande git: {e}")
        return None


def check_git_status():
    """Vérifie si le repository git est à jour"""
    print("Vérification de l'état du repository Git...")
    
    # Vérifier si on est dans un repository git
    if not os.path.exists('.git'):
        print("Erreur: Ce répertoire n'est pas un repository Git")
        return False
    
    # Récupérer les dernières modifications du remote
    print("Récupération des dernières modifications...")
    fetch_result = run_git_command("git fetch")
    if fetch_result is None:
        print("Erreur lors de la récupération des modifications distantes")
        return False
    
    # Vérifier s'il y a des modifications non commitées
    status = run_git_command("git status --porcelain")
    if status is None:
        return False
    
    if status:
        print("Erreur: Il y a des modifications non commitées:")
        print(status)
        print("Veuillez committer toutes les modifications avant la compilation.")
        return False
    
    # Vérifier si la branche locale est à jour avec la branche distante
    local_commit = run_git_command("git rev-parse HEAD")
    remote_commit = run_git_command("git rev-parse @{u}")
    
    if local_commit is None or remote_commit is None:
        print("Erreur lors de la vérification des commits")
        return False
    
    if local_commit != remote_commit:
        print("Erreur: La branche locale n'est pas à jour avec la branche distante")
        print(f"Commit local:  {local_commit}")
        print(f"Commit distant: {remote_commit}")
        print("Veuillez faire un pull ou push selon le cas.")
        return False
    
    print("✓ Repository Git à jour")
    return True


def get_git_hash():
    """Récupère le hash du commit actuel"""
    git_hash = run_git_command("git rev-parse --short HEAD")
    if git_hash is None:
        print("Erreur lors de la récupération du hash Git")
        return None
    
    print(f"Hash Git actuel: {git_hash}")
    return git_hash


def update_hash_git_in_file(new_hash):
    """Met à jour la variable HASH_GIT dans configuration.py"""
    configuration_py_path = "configuration.py"
    
    if not os.path.exists(configuration_py_path):
        print(f"Erreur: Le fichier {configuration_py_path} n'existe pas")
        return False
    
    try:
        # Lire le contenu du fichier
        with open(configuration_py_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Remplacer la ligne HASH_GIT
        pattern = r'HASH_GIT\s*=\s*["\'][^"\']*["\']'
        replacement = f'HASH_GIT = "{new_hash}"'
        
        new_content = re.sub(pattern, replacement, content)
        
        if new_content == content:
            print(f"Attention: La variable HASH_GIT n'a pas été trouvée ou était déjà à {new_hash}")
            return True
        
        # Écrire le nouveau contenu
        with open(configuration_py_path, 'w', encoding='utf-8') as file:
            file.write(new_content)
        
        print(f"✓ HASH_GIT mise à jour avec: {new_hash}")
        return True
        
    except Exception as e:
        print(f"Erreur lors de la mise à jour de HASH_GIT: {e}")
        return False


def set_git_hash_git():
    """Met à jour HASH_GIT avec le hash Git (pour avant compilation)"""
    print("=== Mise à jour de HASH_GIT avec le hash Git ===")

    # Vérifier l'état Git
    if not check_git_status():
        print("\n❌ Mise à jour annulée - Repository Git non à jour")
        return False
    
    # Récupérer le hash Git
    git_hash = get_git_hash()
    if git_hash is None:
        print("\n❌ Mise à jour annulée - Impossible de récupérer le hash Git")
        return False
    
    # Mettre à jour HASH_GIT
    if not update_hash_git_in_file(git_hash):
        print("\n❌ Mise à jour annulée - Impossible de mettre à jour HASH_GIT")
        return False

    print("\n✅ HASH_GIT mise à jour avec le hash Git")
    return True


def set_debug_hash_git():
    """Remet le HASH_GIT à DEBUG (pour après compilation)"""
    print("=== Remise de HASH_GIT à DEBUG ===")

    if not update_hash_git_in_file("DEBUG"):
        print("\n❌ Erreur lors de la remise à DEBUG")
        return False

    print("\n✅ HASH_GIT remis à DEBUG")
    return True


def main():
    """Fonction principale avec gestion des arguments"""
    parser = argparse.ArgumentParser(
        description="Gestionnaire de HASH_GIT pour CAPSYS Banc De Test"
    )
    parser.add_argument(
        "action",
        choices=["git", "debug"],
        help="Action à effectuer: 'git' pour mettre le hash Git, 'debug' pour remettre à DEBUG"
    )
    
    args = parser.parse_args()
    success = False
    
    if args.action == "git":
        success = set_git_hash_git()
    elif args.action == "debug":
        success = set_debug_hash_git()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
