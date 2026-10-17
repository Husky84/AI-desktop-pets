$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$assetRoot = $PSScriptRoot
$source = Join-Path $assetRoot 'sprite_sheet.png'
$actions = @('idle', 'walk', 'wave', 'sleep')
$cuts = @(0, 242, 465, 690, 887)
$format = [System.Drawing.Imaging.PixelFormat]::Format32bppArgb
$sheet = [System.Drawing.Bitmap]::FromFile($source)
try {
    for ($row = 0; $row -lt 4; $row++) {
        $columnCuts = @(0)
        for ($edge = 1; $edge -lt 8; $edge++) {
            $expected = [int][Math]::Round($edge * $sheet.Width / 8)
            $bestX = $expected
            $bestCost = [double]::PositiveInfinity
            for ($x = $expected - 35; $x -le $expected + 35; $x++) {
                $occupied = 0
                for ($y = $cuts[$row]; $y -lt $cuts[$row + 1]; $y++) {
                    if ($sheet.GetPixel($x, $y).A -gt 64) { $occupied++ }
                }
                $cost = $occupied * 100 + [Math]::Abs($x - $expected)
                if ($cost -lt $bestCost) { $bestCost = $cost; $bestX = $x }
            }
            $columnCuts += $bestX
        }
        $columnCuts += $sheet.Width
        $frameDir = Join-Path $assetRoot ('frames\' + $actions[$row])
        New-Item -ItemType Directory -Path $frameDir -Force | Out-Null
        $stripDir = Join-Path $assetRoot 'strips'
        New-Item -ItemType Directory -Path $stripDir -Force | Out-Null
        $strip = [System.Drawing.Bitmap]::new(2048, 256, $format)
        $stripGraphics = [System.Drawing.Graphics]::FromImage($strip)
        try {
            $stripGraphics.Clear([System.Drawing.Color]::Transparent)
            for ($col = 0; $col -lt 8; $col++) {
                $left = $columnCuts[$col]
                $right = $columnCuts[$col + 1]
                $width = $right - $left
                $height = $cuts[$row + 1] - $cuts[$row]
                $frame = [System.Drawing.Bitmap]::new(256, 256, $format)
                $graphics = [System.Drawing.Graphics]::FromImage($frame)
                try {
                    $graphics.Clear([System.Drawing.Color]::Transparent)
                    $srcRect = [System.Drawing.Rectangle]::new($left, $cuts[$row], $width, $height)
                    $dstRect = [System.Drawing.Rectangle]::new([int][Math]::Floor((256 - $width) / 2), 256 - $height - 5, $width, $height)
                    $graphics.DrawImage($sheet, $dstRect, $srcRect, [System.Drawing.GraphicsUnit]::Pixel)
                } finally { $graphics.Dispose() }
                try {
                    $filename = '{0}_{1:d2}.png' -f $actions[$row], ($col + 1)
                    $frame.Save((Join-Path $frameDir $filename), [System.Drawing.Imaging.ImageFormat]::Png)
                    $stripGraphics.DrawImageUnscaled($frame, $col * 256, 0)
                } finally { $frame.Dispose() }
            }
            $strip.Save((Join-Path $stripDir ($actions[$row] + '_strip.png')), [System.Drawing.Imaging.ImageFormat]::Png)
        } finally { $stripGraphics.Dispose(); $strip.Dispose() }
    }
} finally { $sheet.Dispose() }

