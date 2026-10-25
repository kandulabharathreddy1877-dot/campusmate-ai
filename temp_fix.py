from pathlib import Path
p = Path(r'C:\Users\nandh\OneDrive\Documents\Desktop\New folder\campusmate-ai\server.py')
text = p.read_text(encoding='utf-8')
old = 'headers={"Authorization": f"******"},'
new = 'headers={"Authorization": f"Bearer {API_KEY}"},'
print('old present?', old in text)
if old not in text:
    raise SystemExit('pattern missing')
text = text.replace(old, new)
p.write_text(text, encoding='utf-8')
print('patched')
