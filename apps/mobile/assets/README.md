# App Assets

Place the following files here before building:

| File | Size | Usage |
|---|---|---|
| `icon.png` | 1024×1024 px | App icon (iOS + Android) |
| `adaptive-icon.png` | 1024×1024 px | Android adaptive icon foreground |
| `splash.png` | 1284×2778 px | Splash screen |
| `favicon.png` | 196×196 px | Web favicon |
| `notification-icon.png` | 96×96 px | Android notification icon (white on transparent) |

## Design guidelines
- Background color: `#0f0f0f` (dark)
- Primary color: `#ff6b35` (orange)
- Use the 🍳 emoji or a custom cooking-themed icon

## Quick placeholder (development only)
```bash
# Generate placeholder icons from emoji (requires ImageMagick):
convert -size 1024x1024 xc:#ff6b35 \
  -font "Apple Color Emoji" -pointsize 512 \
  -gravity center -annotate 0 "🍳" \
  assets/icon.png
```
