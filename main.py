from __future__ import annotations

import runpy
import sys
from pathlib import Path


if __name__ == "__main__":
    # When launched through `streamlit run main.py`, Streamlit preloads its modules.
    # In that case, execute the dedicated UI script instead of GHunt CLI parser.
    if "streamlit" in sys.modules:
        runpy.run_path(str(Path(__file__).with_name("streamlit_app.py")), run_name="__main__")
    else:
        from ghunt import ghunt

        ghunt.main()