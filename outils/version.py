"""Estampille la version du paquet juste avant sa construction (exécuté par le pipeline).

Sur un tag v1.2.3, la version vaut 1.2.3. Sinon : version de base + .devNNN (NNN = identifiant
de l'exécution), ce qui donne une version unique et triable à chaque passage du pipeline.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

INIT = Path("src/hydroradar/__init__.py")
MOTIF = re.compile(r'__version__ = "(.+?)"')


def calculer(base: str, ref: str, identifiant: str) -> str:
    if ref.startswith("refs/tags/v"):
        return ref.removeprefix("refs/tags/v")
    return f"{base}.dev{identifiant}"


def main() -> int:
    texte = INIT.read_text(encoding="utf-8")
    ref = os.environ.get("BUILD_SOURCEBRANCH", "")
    version = calculer(MOTIF.search(texte).group(1), ref, os.environ.get("BUILD_BUILDID", "0"))
    if not re.fullmatch(r"\d+\.\d+\.\d+(\.dev\d+)?", version):
        print(f"##vso[task.logissue type=error]Version invalide : {version} (attendu : v1.2.3)")
        return 1
    INIT.write_text(MOTIF.sub(f'__version__ = "{version}"', texte), encoding="utf-8")
    print(f"Version du paquet : {version}")
    # Variable de sortie : les stages DEV et PROD la liront pour installer exactement ce paquet.
    print(f"##vso[task.setvariable variable=numero;isOutput=true]{version}")
    if ref.startswith("refs/tags/v"):
        print(f"##vso[build.updatebuildnumber]{version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
