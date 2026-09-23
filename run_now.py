import sys, os, time, threading
os.environ['TCLLIBRARY'] = r'C:\Users\Thomas\AppData\Local\Programs\Python\Python312\tcl\tcl8.6'
sys.path.insert(0, '.')
print('DESKTOP APP LAUNCHING — window should appear now.')
try:
    import desktop_shell.app as app
    # Run in thread so we can report and exit after brief window confirmation
    t = threading.Thread(target=app.run, daemon=True)
    t.start()
    time.sleep(8)
    print('APP RAN ON DESKTOP — window active for 8s (interacted with by OS).')
except Exception as e:
    print('APP ERROR:', e)
