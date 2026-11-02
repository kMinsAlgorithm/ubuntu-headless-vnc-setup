[CmdletBinding()]
param([Parameter(Mandatory=$true)][ValidateSet('full','region')][string]$Mode, [switch]$Check)
$ErrorActionPreference = 'Stop'
if ([Threading.Thread]::CurrentThread.ApartmentState -ne 'STA') { throw 'Start capture with Windows PowerShell -STA.' }
Add-Type -AssemblyName System.Windows.Forms,System.Drawing
Add-Type -ReferencedAssemblies System.Windows.Forms,System.Drawing -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Windows.Forms;
public static class VncCaptureNative {
    [DllImport("user32.dll")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr window, int command);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr window);
    [DllImport("user32.dll")] private static extern IntPtr GetDC(IntPtr window);
    [DllImport("user32.dll")] private static extern int ReleaseDC(IntPtr window, IntPtr dc);
    [DllImport("gdi32.dll", SetLastError=true)] private static extern bool BitBlt(
        IntPtr target,int x,int y,int width,int height,IntPtr source,int sourceX,int sourceY,uint operation);
    public static Bitmap Snapshot(Rectangle bounds) {
        Bitmap bitmap = new Bitmap(bounds.Width,bounds.Height,System.Drawing.Imaging.PixelFormat.Format32bppRgb);
        try {
            using (Graphics graphics = Graphics.FromImage(bitmap)) {
                IntPtr screen = GetDC(IntPtr.Zero);
                if (screen == IntPtr.Zero) throw new Win32Exception();
                IntPtr target = IntPtr.Zero;
                try {
                    target = graphics.GetHdc();
                    if (!BitBlt(target,0,0,bounds.Width,bounds.Height,screen,bounds.Left,bounds.Top,0x40CC0020))
                        throw new Win32Exception(Marshal.GetLastWin32Error());
                } finally {
                    if (target != IntPtr.Zero) graphics.ReleaseHdc(target);
                    ReleaseDC(IntPtr.Zero,screen);
                }
            }
            return bitmap;
        } catch { bitmap.Dispose(); throw; }
    }
}
public sealed class VncCaptureSelection : Form {
    public Rectangle Selection { get; private set; }
    private Point start, current;
    private bool dragging;
    private readonly Bitmap desktop;
    public bool UsesLayeredWindow { get { return (CreateParams.ExStyle & 0x80000) != 0; } }
    public VncCaptureSelection(Rectangle bounds) : this(bounds,null) { }
    public VncCaptureSelection(Rectangle bounds,Bitmap image) {
        desktop = image;
        FormBorderStyle = FormBorderStyle.None;
        StartPosition = FormStartPosition.Manual;
        Bounds = bounds;
        TopMost = true;
        ShowInTaskbar = true;
        BackColor = Color.Black;
        Cursor = Cursors.Cross;
        KeyPreview = true;
        DoubleBuffered = true;
        Text = "VNC \uC601\uC5ED \uCEa1\uCC98 - Esc \uCDE8\uC18C";
    }
    protected override void OnShown(EventArgs e) {
        base.OnShown(e);
        // A hidden/no-console launcher must not hide the first GUI window.
        VncCaptureNative.ShowWindow(Handle,5);
        VncCaptureNative.SetForegroundWindow(Handle);
        Activate();
        Focus();
    }
    private Rectangle DragRectangle() {
        return new Rectangle(Math.Min(start.X,current.X),Math.Min(start.Y,current.Y),
                             Math.Abs(start.X-current.X),Math.Abs(start.Y-current.Y));
    }
    protected override void OnMouseDown(MouseEventArgs e) {
        base.OnMouseDown(e);
        if (e.Button == MouseButtons.Right) { DialogResult = DialogResult.Cancel; Close(); return; }
        if (e.Button != MouseButtons.Left) return;
        start = current = e.Location;
        dragging = true;
        Capture = true;
    }
    protected override void OnMouseMove(MouseEventArgs e) {
        base.OnMouseMove(e);
        if (dragging) { current = e.Location; Invalidate(); }
    }
    protected override void OnMouseUp(MouseEventArgs e) {
        base.OnMouseUp(e);
        if (!dragging || e.Button != MouseButtons.Left) return;
        current = e.Location;
        dragging = false;
        Capture = false;
        Rectangle box = Rectangle.Intersect(DragRectangle(), ClientRectangle);
        if (box.Width < 2 || box.Height < 2) { Invalidate(); return; }
        Selection = new Rectangle(Left+box.Left,Top+box.Top,box.Width,box.Height);
        DialogResult = DialogResult.OK;
        Close();
    }
    protected override void OnKeyDown(KeyEventArgs e) {
        if (e.KeyCode == Keys.Escape) { e.Handled = true; DialogResult = DialogResult.Cancel; Close(); }
        base.OnKeyDown(e);
    }
    protected override void OnPaint(PaintEventArgs e) {
        base.OnPaint(e);
        if (desktop != null) e.Graphics.DrawImageUnscaled(desktop,0,0);
        using (Brush shade = new SolidBrush(Color.FromArgb(85,0,0,0)))
            e.Graphics.FillRectangle(shade,ClientRectangle);
        if (dragging) {
            Rectangle box = DragRectangle();
            if (desktop != null && box.Width > 0 && box.Height > 0)
                e.Graphics.DrawImage(desktop,box,box,GraphicsUnit.Pixel);
            using (Pen pen = new Pen(Color.White,2)) e.Graphics.DrawRectangle(pen,box);
        }
        using (Brush background = new SolidBrush(Color.FromArgb(230,25,25,25)))
            e.Graphics.FillRectangle(background,12,12,370,32);
        e.Graphics.DrawString(Text,SystemFonts.MessageBoxFont,Brushes.White,22,20);
    }
}
'@
function Crop-Frame($frame, $desktopBounds, $selected) {
    $crop = New-Object Drawing.Rectangle ($selected.Left-$desktopBounds.Left),($selected.Top-$desktopBounds.Top),$selected.Width,$selected.Height
    return $frame.Clone($crop,[Drawing.Imaging.PixelFormat]::Format32bppArgb)
}
$null = [VncCaptureNative]::SetThreadDpiAwarenessContext([IntPtr](-4))
$bounds = [Windows.Forms.SystemInformation]::VirtualScreen
if ($Check) {
    $probe = New-Object VncCaptureSelection $bounds
    try { $ready = $probe.Bounds.Width -eq $bounds.Width -and $probe.Bounds.Height -eq $bounds.Height -and -not $probe.UsesLayeredWindow }
    finally { $probe.Dispose() }
    $sample = New-Object Drawing.Bitmap 3,3
    $sampleCrop = $null
    try {
        $sample.SetPixel(1,2,[Drawing.Color]::Red)
        $sampleBounds = New-Object Drawing.Rectangle -100,50,3,3
        $selected = New-Object Drawing.Rectangle -99,52,1,1
        $sampleCrop = Crop-Frame $sample $sampleBounds $selected
        $pixel = $sampleCrop.GetPixel(0,0)
        $ready = $ready -and $sampleCrop.Width -eq 1 -and $sampleCrop.Height -eq 1 -and $pixel.R -eq 255 -and $pixel.G -eq 0 -and $pixel.B -eq 0
    } finally { if ($sampleCrop) { $sampleCrop.Dispose() }; $sample.Dispose() }
    [pscustomobject]@{Ready=$ready;Output='clipboard';OpaqueSelection=$true;Width=$bounds.Width;Height=$bounds.Height} | ConvertTo-Json
    return
}
if ($bounds.Width -lt 1 -or $bounds.Height -lt 1) { throw 'There is no active screen to capture.' }
$frame = [VncCaptureNative]::Snapshot($bounds)
$bitmap = $null
try {
    if ($Mode -eq 'region') {
        $selection = New-Object VncCaptureSelection -ArgumentList $bounds,$frame
        try {
            if ($selection.ShowDialog() -ne [Windows.Forms.DialogResult]::OK) { return }
            $bitmap = Crop-Frame $frame $bounds $selection.Selection
        } finally { $selection.Dispose() }
    } else { $bitmap = $frame }
    # WinForms persists image data after this process exits. No image file is
    # created, and no pre-existing clipboard text or image is read.
    [Windows.Forms.Clipboard]::SetImage($bitmap)
} finally {
    if ($bitmap -and -not [Object]::ReferenceEquals($bitmap,$frame)) { $bitmap.Dispose() }
    $frame.Dispose()
}
