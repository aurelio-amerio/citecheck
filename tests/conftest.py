import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "skills" / "citecheck" / "scripts"))
sys.path.insert(0, str(_ROOT / "skills" / "citecheck-deep" / "scripts"))
