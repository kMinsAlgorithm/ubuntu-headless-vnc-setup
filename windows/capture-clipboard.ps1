[CmdletBinding()]
param([Parameter(Mandatory=$true)][ValidateSet('full','region')][string]$Mode, [switch]$Check)
$ErrorActionPreference = 'Stop'
if ([Threading.Thread]::CurrentThread.ApartmentState -ne 'STA') { throw 'Start capture with Windows PowerShell -STA.' }
Add-Type -AssemblyName System.Windows.Forms,System.Drawing
Add-Type -ReferencedAssemblies System.Windows.Forms,System.Drawing -TypeDefinition @'
using System;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Windows.Forms;
public static class VncCaptureNative {
    [DllImport("user32.dll")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
    [DllImport("dwmapi.dll")] public static extern int DwmFlush();
}
public sealed class VncCaptureSelection : Form {
    public Rectangle Selection { get; private set; }
    private Point start, current;
    private bool dragging;
    public VncCaptureSelection(Rectangle bounds) {
        FormBorderStyle = FormBorderStyle.None;
        StartPosition = FormStartPosition.Manual;
        Bounds = bounds;
        TopMost = true;
        ShowInTaskbar = false;
        BackColor = Color.Black;
        Opacity = 0.25;
        Cursor = Cursors.Cross;
        KeyPreview = true;
        DoubleBuffered = true;
        Text = "VNC \uC601\uC5ED \uCEa1\uCC98 - Esc \uCDE8\uC18C";
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
        if (dragging) using (Pen pen = new Pen(Color.White, 4)) e.Graphics.DrawRectangle(pen, DragRectangle());
    }
}
'@
$null = [VncCaptureNative]::SetThreadDpiAwarenessContext([IntPtr](-4))
$bounds = [Windows.Forms.SystemInformation]::VirtualScreen
if ($Check) {
    $probe = New-Object VncCaptureSelection $bounds
    try { $ready = $probe.Bounds.Width -eq $bounds.Width -and $probe.Bounds.Height -eq $bounds.Height }
    finally { $probe.Dispose() }
    [pscustomobject]@{Ready=$ready;Output='clipboard';Width=$bounds.Width;Height=$bounds.Height} | ConvertTo-Json
    return
}
if ($Mode -eq 'region') {
    $selection = New-Object VncCaptureSelection $bounds
    try {
        if ($selection.ShowDialog() -ne [Windows.Forms.DialogResult]::OK) { return }
        $bounds = $selection.Selection
    } finally { $selection.Dispose() }
    [Windows.Forms.Application]::DoEvents()
    $null = [VncCaptureNative]::DwmFlush()
    Start-Sleep -Milliseconds 120
}
if ($bounds.Width -lt 1 -or $bounds.Height -lt 1) { throw 'There is no active screen to capture.' }
$bitmap = New-Object Drawing.Bitmap $bounds.Width,$bounds.Height
try {
    $graphics = [Drawing.Graphics]::FromImage($bitmap)
    try { $graphics.CopyFromScreen($bounds.Location,[Drawing.Point]::Empty,$bounds.Size,[Drawing.CopyPixelOperation]::SourceCopy) }
    finally { $graphics.Dispose() }
    # WinForms persists image data after this process exits. No image file is
    # created, and no pre-existing clipboard text or image is read.
    [Windows.Forms.Clipboard]::SetImage($bitmap)
} finally { $bitmap.Dispose() }
