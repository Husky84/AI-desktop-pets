$ErrorActionPreference = 'Stop'
$assetRoot = Split-Path -Parent $PSScriptRoot
$generationRoot = 'C:\Users\Administrator\.codex\generated_images\01a0ebbc-3caa-7f93-805f-d035ab965e77'
Add-Type -Path (Join-Path $PSScriptRoot 'AlphaAssets.cs') -ReferencedAssemblies System.Drawing.Common,System.Drawing.Primitives,System.Private.Windows.GdiPlus,System.Private.Windows.Core,System.Runtime,System.Linq,System.Collections
$liveRoot = Join-Path $assetRoot 'live2d_preparation'
$partRoot = Join-Path $liveRoot 'parts'
New-Item -ItemType Directory -Path $partRoot -Force | Out-Null
$sheet = Join-Path $assetRoot 'sprite_sheet.png'
[AlphaAssets]::NormalizeFile((Join-Path $generationRoot 'exec-eeeecec6-21de-4472-b487-349642c7f912.png'), $sheet)
[AlphaAssets]::SplitSprites($sheet, $assetRoot)
[AlphaAssets]::NormalizeFile((Join-Path $generationRoot 'exec-e00a8cd0-d080-4729-8064-d30d75757f0f.png'), (Join-Path $liveRoot 'neutral_front.png'))
$atlas = Join-Path $liveRoot 'parts_atlas.png'
[AlphaAssets]::NormalizeFile((Join-Path $generationRoot 'exec-5807d88c-998f-45be-b97c-c7d047b16417.png'), $atlas)
$parts = @(
    @{Name='01_face_base'; Box=@(0,0,309,344)},
    @{Name='02_back_hair_draft'; Box=@(309,0,635,344)},
    @{Name='03_front_hair'; Box=@(635,0,980,344)},
    @{Name='04_ahoge'; Box=@(980,0,1254,344)},
    @{Name='05_horn_viewer_left'; Box=@(0,344,310,640)},
    @{Name='06_horn_viewer_right'; Box=@(310,344,628,640)},
    @{Name='07_eye_viewer_left'; Box=@(628,344,940,605)},
    @{Name='08_eye_viewer_right'; Box=@(940,344,1254,605)},
    @{Name='09_mouth_nose'; Box=@(0,640,305,925)},
    @{Name='10_monocle'; Box=@(305,640,610,925)},
    @{Name='11_torso_draft'; Box=@(610,605,960,918)},
    @{Name='12_backpack'; Box=@(960,605,1254,918)},
    @{Name='13_arm_viewer_left'; Box=@(0,925,320,1254)},
    @{Name='14_arm_viewer_right'; Box=@(320,925,630,1254)},
    @{Name='15_leg_viewer_left'; Box=@(630,918,945,1254)},
    @{Name='16_leg_viewer_right'; Box=@(945,918,1254,1254)}
)
$paths = [System.Collections.Generic.List[string]]::new()
$names = [System.Collections.Generic.List[string]]::new()
$xs = [System.Collections.Generic.List[int]]::new()
$ys = [System.Collections.Generic.List[int]]::new()
foreach ($part in $parts) {
    $path = Join-Path $partRoot ($part.Name + '.png')
    $box = $part.Box
    [AlphaAssets]::CropPart($atlas, $path, $box[0], $box[1], $box[2], $box[3])
    $paths.Add($path); $names.Add($part.Name); $xs.Add($box[0]); $ys.Add($box[1])
}
[AlphaAssets]::WritePartsPSD($atlas, $paths.ToArray(), $names.ToArray(), $xs.ToArray(), $ys.ToArray(), (Join-Path $liveRoot 'parts_board_DRAFT.psd'))
Write-Output 'Built 32 action frames, 4 strips, frontal art, 16 part PNGs, and a 16-layer PSD parts board.'
