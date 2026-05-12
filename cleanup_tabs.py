import re

path = r'C:\Githubdesktop\influence-radar-lui\influence-radar.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

orig_len = len(content)

# 1. 탭 버튼 3개 제거
content = re.sub(
    r'  <button class="nav-btn" onclick="switchTab\(\'map\'.*?</button>\s*',
    '', content, flags=re.DOTALL)
content = re.sub(
    r'  <button class="nav-btn" onclick="switchTab\(\'pattern\'.*?</button>\s*',
    '', content, flags=re.DOTALL)
content = re.sub(
    r'  <button class="nav-btn" onclick="switchTab\(\'news\'.*?</button>\s*',
    '', content, flags=re.DOTALL)

# 2. 탭 div 3개 제거
content = re.sub(r'  <div class="tab" id="tab-map"></div>\n', '', content)
content = re.sub(r'  <div class="tab" id="tab-pattern"></div>\n', '', content)
content = re.sub(r'  <div class="tab" id="tab-news"></div>\n', '', content)

# 3. switchTab case 3개 제거
content = re.sub(r"      case 'map': renderMap\(\); break;\n", '', content)
content = re.sub(r"      case 'pattern': renderPattern\(\); break;\n", '', content)
content = re.sub(r"      case 'news': renderNews\(\); break;\n", '', content)

# 4. renderMap 함수 제거 (다음 // === 섹션 직전까지)
content = re.sub(
    r'\nfunction renderMap\(\)\{.*?\n\}\n\n// ═',
    '\n// ═', content, flags=re.DOTALL)

# 5. RENDER: PATTERN 섹션 + renderPattern 함수 제거
content = re.sub(
    r'\n// ═+\n// RENDER: PATTERN\n// ═+\nfunction renderPattern\(\)\{.*?\n\}\n',
    '\n', content, flags=re.DOTALL)

# 6. forceNewsCheck + renderNews + saveGNewsKey 3함수 제거
content = re.sub(
    r'\nfunction forceNewsCheck\(\)\{.*?\nfunction resetLearn',
    '\nfunction resetLearn', content, flags=re.DOTALL)

new_len = len(content)
print(f'제거됨: {orig_len - new_len:,} 글자')
print(f'최종: {new_len:,} 글자')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('저장 완료')
