import sys
from pathlib import Path

SCRIPTS = Path(__file__).parent.parent / "skills" / "citecheck" / "scripts"
sys.path.insert(0, str(SCRIPTS))
