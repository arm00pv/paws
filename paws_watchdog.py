import subprocess, sys, os, time
code = 'import urllib.request\n'
code += 'try:\n    with urllib.request.urlopen("http://127.0.0.1:8235/api/v1/health", timeout=5) as r:\n        sys.exit(0 if r.status==200 else 1)\nexcept Exception:\n    sys.exit(1)\n'
r = subprocess.run([sys.executable, "-c", code])
if r.returncode != 0:
    p = subprocess.Popen([sys.executable, "-u", "/home/zixen15/paws/backend/paws_api.py"],
                         cwd="/home/zixen15/paws/backend",
                         env={**os.environ, "PAWS_PORT": "8235"},
                         stdout=open("/tmp/paws_api.log", "a"), stderr=subprocess.STDOUT)
    print("paws restarted", time.time())
