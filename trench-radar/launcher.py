# PyInstaller entry script (a package-relative module can't be the entry point directly).
from radar.desktop import main

if __name__ == "__main__":
    main()
