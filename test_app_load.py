import sys, os
sys.path.insert(0, '.')
try:
    import desktop_shell.app as app
    print("APP IMPORT OK")
    # Don't call run() to avoid blocking window; just verify module loads
except Exception as e:
    print("APP IMPORT FAIL:", e)
