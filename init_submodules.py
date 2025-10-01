import subprocess
import os

def update_submodules():
    try:
        # Se place dans le dossier racine du projet
        project_root = os.path.dirname(os.path.abspath(__file__))
        os.chdir(project_root)

        print("🔄 Mise à jour des submodules...")
        subprocess.run(["git", "submodule", "update", "--init", "--recursive", "--remote"], check=True)
        print("✅ Submodules à jour.")

    except subprocess.CalledProcessError as e:
        print(f"❌ Erreur lors de la mise à jour des submodules : {e}")
    except Exception as e:
        print(f"❌ Erreur inattendue : {e}")

# Appelle la fonction automatiquement à l'ouverture du script
if __name__ == "__main__":
    update_submodules()