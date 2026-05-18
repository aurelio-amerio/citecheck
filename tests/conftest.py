import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / ".claude" / "skills" / "citecheck" / "scripts"))
sys.path.insert(0, str(_ROOT / ".claude" / "skills" / "citecheck-deep" / "scripts"))
