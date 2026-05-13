import re, subprocess, sys

path = r'C:\Githubdesktop\influence-radar-lui\influence-radar.html'
with open(path, encoding='utf-8') as f:
    c = f.read()

scripts = re.findall(r'<script[^>]*>(.*?)</script>', c, re.DOTALL)
js = '\n'.join(scripts)

out = r'C:\Githubdesktop\influence-radar-lui\_check.js'
with open(out, 'w', encoding='utf-8') as f:
    f.write(js)

result = subprocess.run(['node', '--check', out], capture_output=True, text=True, encoding='utf-8', errors='replace')
if result.returncode == 0:
    print('OK - no syntax error')
else:
    print('ERROR:')
    print(result.stderr[:3000])
