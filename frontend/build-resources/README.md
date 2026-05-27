# build-resources

Place platform icon files here before running `electron-builder`:

| File | Used for |
|------|----------|
| `icon.ico` | Windows installer + taskbar (256×256 multi-size ICO) |
| `icon.icns` | macOS DMG + dock |
| `icon.png` | Linux AppImage (512×512 PNG) |

To generate all formats from a single 1024×1024 PNG:

```bash
# macOS
brew install imagemagick
magick icon-1024.png -define icon:auto-resize=256,128,64,48,32,16 icon.ico
magick icon-1024.png icon.icns   # requires macOS iconutil

# Windows (with ImageMagick installed)
magick icon-1024.png -resize 256x256 icon.ico

# Linux — any 512×512 PNG works
cp icon-1024.png icon.png
```

`license.txt` is displayed in the Windows NSIS installer.
