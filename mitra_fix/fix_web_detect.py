# fix_web_detect.py – automatically repair empty try blocks in web_detect_status.py

from pathlib import Path

p = Path('/home/pi/rover/web_detect_status.py')  # Pi path
backup = Path('/home/pi/rover/web_detect_status.py.autobak')

print("Backing up original file to:", backup)
backup.write_text(p.read_text())

s = p.read_text()
lines = s.splitlines()
out = []
i = 0
changed = False

while i < len(lines):
    line = lines[i]
    out.append(line)
    stripped = line.lstrip()

    if stripped.startswith("try:"):
        indent = line[:len(line) - len(stripped)]

        j = i + 1
        while j < len(lines) and lines[j].strip() == "":
            out.append(lines[j])
            j += 1

        if j >= len(lines):
            out.append(indent + "    pass")
            changed = True
            break

        next_line = lines[j]
        next_strip = next_line.lstrip()
        next_indent = next_line[:len(next_line) - len(next_strip)]

        if (next_strip.startswith("except") or next_strip.startswith("finally")) and len(next_indent) <= len(indent):
            out.append(indent + "    pass")
            changed = True

    i += 1

new_text = "\n".join(out)
p.write_text(new_text)

print("Fix complete.")
print("Changes applied?" , changed)


