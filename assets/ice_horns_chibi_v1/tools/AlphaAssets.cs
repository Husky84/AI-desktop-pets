using System;
using System.IO;
using System.Text;
using System.Linq;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Collections.Generic;

public static class AlphaAssets
{
    public sealed class Component
    {
        public int Id, Count, X, Y, Width, Height;
        public double CenterX { get { return X + Width / 2.0; } }
        public double CenterY { get { return Y + Height / 2.0; } }
    }

    public static Bitmap Normalize(string path)
    {
        using (var source = new Bitmap(path))
        {
            var result = new Bitmap(source.Width, source.Height, PixelFormat.Format32bppArgb);
            using (var g = Graphics.FromImage(result))
            {
                g.Clear(Color.FromArgb(0, 0, 0, 0));
                g.DrawImageUnscaled(source, 0, 0);
            }
            return result;
        }
    }

    public static void NormalizeFile(string input, string output)
    {
        using (var bitmap = Normalize(input)) bitmap.Save(output, ImageFormat.Png);
    }

    private static byte[] Pixels(Bitmap bitmap)
    {
        var data = bitmap.LockBits(new Rectangle(0, 0, bitmap.Width, bitmap.Height), ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
        try
        {
            var bytes = new byte[bitmap.Width * bitmap.Height * 4];
            for (int y = 0; y < bitmap.Height; y++)
                Marshal.Copy(IntPtr.Add(data.Scan0, y * data.Stride), bytes, y * bitmap.Width * 4, bitmap.Width * 4);
            return bytes;
        }
        finally { bitmap.UnlockBits(data); }
    }

    private static List<Component> Find(byte[] pixels, int width, int height, out int[] labels)
    {
        labels = new int[width * height];
        var queue = new int[width * height];
        var list = new List<Component>();
        int id = 0;
        for (int start = 0; start < labels.Length; start++)
        {
            if (labels[start] != 0 || pixels[start * 4 + 3] < 128) continue;
            id++;
            int head = 0, tail = 0, minX = width, minY = height, maxX = 0, maxY = 0;
            queue[tail++] = start;
            labels[start] = id;
            while (head < tail)
            {
                int p = queue[head++], x = p % width, y = p / width;
                minX = Math.Min(minX, x); maxX = Math.Max(maxX, x);
                minY = Math.Min(minY, y); maxY = Math.Max(maxY, y);
                for (int dy = -1; dy <= 1; dy++) for (int dx = -1; dx <= 1; dx++)
                {
                    int nx = x + dx, ny = y + dy;
                    if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
                    int n = ny * width + nx;
                    if (labels[n] == 0 && pixels[n * 4 + 3] >= 128)
                    { labels[n] = id; queue[tail++] = n; }
                }
            }
            list.Add(new Component { Id = id, Count = tail, X = minX, Y = minY, Width = maxX - minX + 1, Height = maxY - minY + 1 });
        }
        return list;
    }

    public static Component[] Analyze(string path, int minimum)
    {
        using (var bitmap = Normalize(path))
        {
            int[] labels;
            return Find(Pixels(bitmap), bitmap.Width, bitmap.Height, out labels).Where(c => c.Count >= minimum).OrderBy(c => c.Y).ToArray();
        }
    }

    public static void SplitSprites(string source, string root)
    {
        string[] actions = { "idle", "walk", "wave", "sleep" };
        using (var bitmap = Normalize(source))
        {
            var pixels = Pixels(bitmap);
            int[] labels;
            var components = Find(pixels, bitmap.Width, bitmap.Height, out labels).Where(c => c.Count >= 1000).ToList();
            if (components.Count != 32) throw new InvalidDataException("Expected 32 isolated sprites, found " + components.Count);
            components = components.OrderBy(c => c.CenterY).ToList();
            int size = 320;
            Directory.CreateDirectory(Path.Combine(root, "strips"));
            for (int row = 0; row < 4; row++)
            {
                var group = components.Skip(row * 8).Take(8).OrderBy(c => c.CenterX).ToList();
                int maxHeight = group.Max(c => c.Height);
                Directory.CreateDirectory(Path.Combine(root, "frames", actions[row]));
                using (var strip = new Bitmap(size * 8, size, PixelFormat.Format32bppArgb))
                using (var stripGraphics = Graphics.FromImage(strip))
                {
                    stripGraphics.Clear(Color.FromArgb(0, 0, 0, 0));
                    for (int col = 0; col < 8; col++)
                    {
                        var c = group[col];
                        if (c.Width > size - 12 || c.Height > size - 12) throw new InvalidDataException("Sprite exceeds canvas");
                        using (var frame = new Bitmap(size, size, PixelFormat.Format32bppArgb))
                        {
                            int left = (size - c.Width) / 2;
                            int top = size - maxHeight - 12 + (maxHeight - c.Height);
                            // Copy this connected character only, retaining its antialias edge.
                            for (int y = -2; y < c.Height + 2; y++) for (int x = -2; x < c.Width + 2; x++)
                            {
                                int sx = c.X + x, sy = c.Y + y, tx = left + x, ty = top + y;
                                if (sx < 0 || sy < 0 || sx >= bitmap.Width || sy >= bitmap.Height || tx < 0 || ty < 0 || tx >= size || ty >= size) continue;
                                bool belongs = false;
                                for (int dy = -1; dy <= 1 && !belongs; dy++) for (int dx = -1; dx <= 1; dx++)
                                {
                                    int nx = sx + dx, ny = sy + dy;
                                    if (nx >= 0 && ny >= 0 && nx < bitmap.Width && ny < bitmap.Height && labels[ny * bitmap.Width + nx] == c.Id) { belongs = true; break; }
                                }
                                if (belongs) frame.SetPixel(tx, ty, bitmap.GetPixel(sx, sy));
                            }
                            frame.Save(Path.Combine(root, "frames", actions[row], actions[row] + "_" + (col + 1).ToString("D2") + ".png"), ImageFormat.Png);
                            stripGraphics.DrawImageUnscaled(frame, col * size, 0);
                        }
                    }
                    strip.Save(Path.Combine(root, "strips", actions[row] + "_strip.png"), ImageFormat.Png);
                }
            }
        }
    }

    public static void CropPart(string source, string output, int left, int top, int right, int bottom)
    {
        using (var bitmap = Normalize(source))
        using (var part = new Bitmap(right - left, bottom - top, PixelFormat.Format32bppArgb))
        using (var g = Graphics.FromImage(part))
        {
            g.Clear(Color.FromArgb(0, 0, 0, 0));
            g.DrawImage(bitmap, new Rectangle(0, 0, part.Width, part.Height), new Rectangle(left, top, part.Width, part.Height), GraphicsUnit.Pixel);
            part.Save(output, ImageFormat.Png);
        }
    }

    private static void U16(BinaryWriter w, int value) { w.Write((byte)(value >> 8)); w.Write((byte)value); }
    private static void U32(BinaryWriter w, long value) { w.Write((byte)(value >> 24)); w.Write((byte)(value >> 16)); w.Write((byte)(value >> 8)); w.Write((byte)value); }
    private static void Text(BinaryWriter w, string value) { w.Write(Encoding.ASCII.GetBytes(value)); }
    private static byte[] Block(Action<BinaryWriter> write)
    {
        using (var stream = new MemoryStream())
        { using (var w = new BinaryWriter(stream, Encoding.ASCII, true)) write(w); return stream.ToArray(); }
    }

    // Standard PSD v1, 8-bit RGB, real independently editable raster layers.
    public static void WritePartsPSD(string atlas, string[] paths, string[] names, int[] xs, int[] ys, string output)
    {
        using (var composite = Normalize(atlas))
        {
            var bitmaps = paths.Select(p => Normalize(p)).ToArray();
            try
            {
                var layerPixels = bitmaps.Select(b => Pixels(b)).ToArray();
                byte[] info = Block(w =>
                {
                    U16(w, -bitmaps.Length); // Negative layer count marks merged transparency.
                    for (int i = bitmaps.Length - 1; i >= 0; i--)
                    {
                        var b = bitmaps[i];
                        U32(w, ys[i]); U32(w, xs[i]); U32(w, ys[i] + b.Height); U32(w, xs[i] + b.Width);
                        U16(w, 4);
                        foreach (int ch in new int[] { -1, 0, 1, 2 }) { U16(w, ch); U32(w, 2 + b.Width * b.Height); }
                        Text(w, "8BIMnorm"); w.Write((byte)255); w.Write((byte)0); w.Write((byte)0); w.Write((byte)0);
                        byte[] extra = Block(e =>
                        {
                            U32(e, 0); U32(e, 0);
                            byte[] name = Encoding.ASCII.GetBytes(names[i]); int n = Math.Min(255, name.Length);
                            e.Write((byte)n); e.Write(name, 0, n);
                            int pad = (4 - ((n + 1) % 4)) % 4; e.Write(new byte[pad]);
                        });
                        U32(w, extra.Length); w.Write(extra);
                    }
                    for (int i = bitmaps.Length - 1; i >= 0; i--)
                    foreach (int ch in new int[] { 3, 2, 1, 0 })
                    {
                        U16(w, 0);
                        for (int p = ch; p < layerPixels[i].Length; p += 4) w.Write(layerPixels[i][p]);
                    }
                });
                if (info.Length % 2 != 0) Array.Resize(ref info, info.Length + 1);
                byte[] mask = Block(w => { U32(w, info.Length); w.Write(info); U32(w, 0); });
                using (var stream = File.Create(output)) using (var w = new BinaryWriter(stream))
                {
                    Text(w, "8BPS"); U16(w, 1); w.Write(new byte[6]); U16(w, 4);
                    U32(w, composite.Height); U32(w, composite.Width); U16(w, 8); U16(w, 3);
                    U32(w, 0); U32(w, 0); U32(w, mask.Length); w.Write(mask);
                    U16(w, 0); var rgba = Pixels(composite);
                    foreach (int ch in new int[] { 2, 1, 0, 3 }) for (int p = ch; p < rgba.Length; p += 4) w.Write(rgba[p]);
                }
            }
            finally { foreach (var b in bitmaps) b.Dispose(); }
        }
    }
}
